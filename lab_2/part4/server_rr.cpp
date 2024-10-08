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
#include <queue>
#include <atomic>
#include <thread>
#include <map>
#include <algorithm>
#include "json.hpp"

using namespace std;
using json = nlohmann::json;

vector<string> word_list;
atomic<int> client_count(0);
atomic<bool> server_running(true);
atomic<int> active_requests(0);

struct ClientRequest {
    int client_socket;
    int offset;
};

map<int, queue<ClientRequest>> client_queues;
map<int, bool> client_served;
pthread_mutex_t queue_mutex = PTHREAD_MUTEX_INITIALIZER;

int k, p, num_clients;
int server_socket;

void splitWordsFromFile(const string& input) {
    istringstream stream(input);
    string word;
    while (getline(stream, word, ',')) {
        word_list.push_back(word);
    }
}

void* workerThread(void* arg) {
    while (server_running) {
        pthread_mutex_lock(&queue_mutex);
        for (auto it = client_queues.begin(); it != client_queues.end(); ++it) {
            if (!it->second.empty()) {
                ClientRequest request = it->second.front();
                it->second.pop();

                pthread_mutex_unlock(&queue_mutex);

                int offset = request.offset;
                int client_socket = request.client_socket;

                if (offset >= word_list.size()) {
                    send(client_socket, "$$\n", 3, 0);
                    client_served[client_socket] = true;
                    continue;
                }

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
                        client_served[client_socket] = true;
                    }
                    pkt += '\n';
                    send(client_socket, pkt.c_str(), pkt.length(), 0);
                    // cout << client_socket << endl;
                }

                pthread_mutex_lock(&queue_mutex);
            }
        }
        pthread_mutex_unlock(&queue_mutex);
    }
    return nullptr;
}

void* handleClient(void* arg) {
    int client_socket = *((int*)arg);
    delete (int*)arg;

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

        pthread_mutex_lock(&queue_mutex);
        client_queues[client_socket].push({client_socket, offset});
        pthread_mutex_unlock(&queue_mutex);
    }
    return nullptr;
}

void monitorConnections() {
    while (server_running) {
        pthread_mutex_lock(&queue_mutex);
        for (auto it = client_queues.begin(); it != client_queues.end();) {
            if (client_served[it->first] && it->second.empty()) {
                close(it->first);
                //cout << "Closed connection for client " << it->first << endl;
                it = client_queues.erase(it);
            }
            else {
                ++it;
            }
        }
        pthread_mutex_unlock(&queue_mutex);
        this_thread::sleep_for(chrono::seconds(1)); // Monitor every second
    }
}

int main() {
    // Read config.json
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    k = config["k"];
    p = config["p"];
    num_clients = config["num_clients"];
    string input_file = config["input_file"];

    ifstream file(input_file);
    stringstream buffer;
    buffer << file.rdbuf();
    splitWordsFromFile(buffer.str());

    server_socket = socket(PF_INET, SOCK_STREAM, 0);
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
    inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr);

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

    //cout << "Server listening on " << server_ip << ":" << server_port << endl;

    pthread_t worker_thread;
    if (pthread_create(&worker_thread, NULL, workerThread, NULL) != 0) {
        cerr << "Failed to create worker thread" << endl;
        return -1;
    }

    thread monitor_thread(monitorConnections);

    while (server_running) {
        sockaddr_in client_addr;
        socklen_t client_size = sizeof(client_addr);
        int* client_socket = new int(accept(server_socket, (struct sockaddr*)&client_addr, &client_size));

        if (*client_socket == -1) {
            delete client_socket;
            if (!server_running) break;
            cerr << "Accept failed" << endl;
            continue;
        }

        pthread_t client_thread;
        if (pthread_create(&client_thread, NULL, handleClient, (void*)client_socket) != 0) {
            cerr << "Failed to create client thread" << endl;
            close(*client_socket);
            delete client_socket;
        }
        pthread_detach(client_thread);
    }

    pthread_join(worker_thread, NULL);
    server_running = false;
    monitor_thread.join();
    close(server_socket);
    return 0;
}
