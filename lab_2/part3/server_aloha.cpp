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
#include <chrono>
#include <atomic>
#include "json.hpp"
using namespace std;

struct ServerState{
    atomic<bool> collision = false;
    atomic<long long> initialized = -1;
};

using json = nlohmann::json;
vector<string> word_list;
atomic<int> client_count = 0;
ServerState server_state;

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
    int T;
};

void* handleClient(void* arg) {

    Info* info = (Info*)arg;
    int client_socket = info->client_socket;
    int T = info->T;
    int num_clients = info->num_clients;
    int server_socket = info->server_socket;
    delete info;

    auto now = chrono::system_clock::now();
    auto duration = chrono::duration_cast<chrono::milliseconds>(now.time_since_epoch());
    long long t = duration.count();
    server_state.initialized.store(t/T);

    char buffer[1024];
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int ret = recv(client_socket, buffer, sizeof(buffer), 0);
        if (ret <= 0) {
            close(client_socket);
            return nullptr;
        }

        now = chrono::system_clock::now();
        duration = chrono::duration_cast<chrono::milliseconds>(now.time_since_epoch());
        t = duration.count();

        long long slot_no = t/T;
        // cout << "t " << t << "T " << T << endl; 
        // cout << slot_no << endl;

        if (slot_no != server_state.initialized){
            server_state.initialized.store(slot_no);
            server_state.collision.store(false);
            // cout << "nocollision" << endl;
        }
        else if (!server_state.collision){
            // cout << "collision" << endl;
            server_state.collision.store(true);
        }

        string request(buffer);
        int offset = stoi(request);
        // cout << "Request " << request << endl;
        if (offset >= word_list.size()) {
            send(client_socket, "$$\n", 3, 0);
            return nullptr;
        }

        int words_sent = 0;
        while (words_sent < 10 && offset + words_sent < word_list.size()) {
            string pkt = word_list[offset + words_sent];
            if (offset + words_sent >= word_list.size()-1) {
                pkt += ",EOF";
            }
            pkt += '\n';
            // cout << "Packet for client " << client_socket << ": " << pkt;
            if (!server_state.collision){
                send(client_socket, pkt.c_str(), pkt.length(), 0);
            }
            else{
                send(client_socket, "HUH!\n", 5, 0);
                break;
            }
            words_sent++;
        }

        if (offset + words_sent >= word_list.size()) {
            close(client_socket);
            client_count++;
            // cout << "Server has served " << client_count << " clients." << endl;
            if (client_count >= num_clients) {
                cout << "Server has served " << num_clients << " clients, shutting down." << endl;
                close(server_socket);
            }
            return nullptr;
        }
    }
    return 0;
}

int main(){

    // Read config.json
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int T = config["T"];
    int num_clients = config["num_clients"];
    string input_file = config["input_file"];

    // Memory-map the input file
    ifstream file(input_file);
    stringstream buffer;
    buffer << file.rdbuf();
    splitWordsFromFile(buffer.str());

    // Create server socket
    int server_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (server_socket == -1) {
        cerr << "Error creating socket: " << strerror(errno) << endl;
        return -1;
    }

    // Set socket option to allow address reuse
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
    
    // Convert IP address from string to binary form
    if (inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr) <= 0) {
        cerr << "Invalid IP address: " << server_ip << endl;
        close(server_socket);
        return -1;
    }

    // Bind the socket
    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
        cerr << "Bind failed: " << strerror(errno) << endl;
        close(server_socket);
        return -1;
    }

    // Listen for incoming connections
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
            cerr << "Accept failed" << endl;
            return 0;
        }

        Info* info =  new Info;
        info->client_socket = client_socket;
        info->T = T;
        info->num_clients = num_clients;
        info->server_socket = server_socket;

        pthread_t client_thread;
        if (pthread_create(&client_thread, NULL, handleClient, (void*)info) != 0) {
            cerr << "Failed to create thread" << endl;
            close(client_socket);
        }
        pthread_detach(client_thread);
    }

    close(server_socket);
    return 0;
}
