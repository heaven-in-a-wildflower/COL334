#include <iostream>
#include <fstream>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstring>
#include <arpa/inet.h>
#include <pthread.h>
#include <vector>
#include <map>
#include <sys/mman.h>
#include <atomic>
#include "json.hpp"

using namespace std;

using json = nlohmann::json;
vector<string> word_list;
atomic<int> client_count(0);

void splitWordsFromFile(const string& input) {
    istringstream stream(input);
    string word;
    while (getline(stream, word, ',')){
        word_list.push_back(word);
    }
}

struct Info{
    int client_socket;
    int server_socket;
    int num_clients;
    int k;
    int p;
};

void* handleClient(void* arg){

    Info* info = (Info*)arg;
    int client_socket = info->client_socket;
    int k = info->k;
    int p = info->p;
    int num_clients = info->num_clients;
    int server_socket = info->server_socket;
    delete info;

    char buffer[1024];
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int ret = recv(client_socket, buffer, sizeof(buffer), 0);
        if (ret <= 0) {
            close(client_socket);
            return nullptr;
        }

        string request(buffer);
        int offset = stoi(request);

        if (offset >= word_list.size()) {
            send(client_socket, "$$\n", 3, 0);
            return nullptr;
        }

        // Send words from offset
        int words_sent = 0;
        while (words_sent < k && offset + words_sent < word_list.size()) {
            string pkt = word_list[offset + words_sent];
            words_sent++;
            for (int i = 1; i < p && words_sent < k && offset + words_sent < word_list.size(); ++i) {
                pkt += "," + word_list[offset + words_sent];
                words_sent++;
            }
            if (offset + words_sent >= word_list.size()) {
                pkt += ",EOF";
            }
            pkt += '\n';
            // cout << "Packet: " << pkt;
            send(client_socket, pkt.c_str(), pkt.length(), 0);
        }

        if (offset + words_sent >= word_list.size()) {
            close(client_socket);
            client_count++;
            cout << client_count << endl;
            if (client_count >= num_clients) {
                cout << "Server has served " << num_clients << " clients, shutting down." << endl;
                close(server_socket);
            }
            return nullptr;
        }
    }
    return 0;
}

int main() {
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int k = config["k"];
    int p = config["p"];
    int num_clients = config["num_clients"];
    string input_file = config["input_file"];

    ifstream file(input_file);
    stringstream buffer;
    buffer << file.rdbuf();
    splitWordsFromFile(buffer.str());

    int server_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (server_socket == -1) {
        cerr << "Error creating socket: " << strerror(errno) << endl;
        return -1;
    }

    int optval = 1;
    if (setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval)) == -1) {
        cerr << "Failed to set SO_REUSEADDR: " << strerror(errno) << endl;
        close(server_socket);
        return -1;
    }

    sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    
    if (inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr) <= 0) {
        cerr << "Invalid IP address: " << server_ip << endl;
        close(server_socket);
        return -1;
    }

    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
        cerr << "Bind failed: " << strerror(errno) << endl;
        close(server_socket);
        return -1;
    }

    if (listen(server_socket, 32) == -1) {
        cerr << "Listen failed: " << strerror(errno) << endl;
        close(server_socket);
        return -1;
    }

    cout << "Server listening on " << server_ip << ":" << server_port << endl;

    while (true) {
        sockaddr_in client_addr;
        socklen_t client_size = sizeof(client_addr);

        int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_size);

        if (client_socket == -1) {
            // cerr << "Accept failed" << std::endl;
            return 0;
        }

        Info* info =  new Info;
        info->client_socket = client_socket;
        info->k = k;
        info->p = p;
        info->num_clients = num_clients;
        info->server_socket = server_socket;

        pthread_t client_thread;
        if (pthread_create(&client_thread, NULL, handleClient, (void*)info) != 0) {
            cerr << "Failed to create thread" << std::endl;
            close(client_socket);
        }
        pthread_detach(client_thread);
    }

    close(server_socket);
    return 0;
}
