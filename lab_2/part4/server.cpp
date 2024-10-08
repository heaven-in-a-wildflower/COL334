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

queue<ClientRequest> request_queue;
pthread_mutex_t queue_mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t queue_cond = PTHREAD_COND_INITIALIZER;

int k, p, num_clients;
int server_socket;

// Function to split words from the input file
void splitWordsFromFile(const string& input) {
    istringstream stream(input);
    string word;
    while (getline(stream, word, ',')) {
        word_list.push_back(word);
    }
}

// Modified worker thread function (handles all client requests)
void* workerThread(void* arg) {
    while (server_running) {
        ClientRequest request;

        pthread_mutex_lock(&queue_mutex);
        while (request_queue.empty() && server_running) {
            pthread_cond_wait(&queue_cond, &queue_mutex);
        }
        if (!server_running && request_queue.empty()) {
            pthread_mutex_unlock(&queue_mutex);
            break;
        }

        request = request_queue.front();
        request_queue.pop();
        active_requests++;
        pthread_mutex_unlock(&queue_mutex);

        // Process the request
        int offset = request.offset;
        int client_socket = request.client_socket;

        if (offset >= word_list.size()) {
            send(client_socket, "$$\n", 3, 0);
            active_requests--;
            continue;
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
                client_count++;
            }
            pkt += '\n';
            //cout << "Packet for client " << client_socket << ": "<<  pkt << endl;
            send(client_socket, pkt.c_str(), pkt.length(), 0);
        }

        // if (offset + words_sent >= word_list.size()) {
        //     close(client_socket);
        // }
        active_requests--;
    }
    return nullptr;
}

// Client handling function
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

        // Enqueue the client request
        pthread_mutex_lock(&queue_mutex);
        request_queue.push({client_socket, offset});
        //cout << "Queued request from client socket: " << client_socket << endl;
        pthread_cond_signal(&queue_cond);
        pthread_mutex_unlock(&queue_mutex);

        // If this is the last request for this client, break the loop
        // if (offset + k >= word_list.size()) {
        //     break;
        // }
    }
    return nullptr;
}

vector<int> active_client_sockets;

void monitorQueue() {
    while (server_running) {
        pthread_mutex_lock(&queue_mutex);
        cout << "QUEUE LENGTH: " << request_queue.size() << endl;
        cout << "QUEUE FRONT: " << request_queue.front().client_socket << ' ' << request_queue.front().offset << endl;
        cout << active_requests << ' ' << client_count<< endl;
        if (request_queue.empty() && active_requests == 0 && client_count >= num_clients) {
            //cout << "All clients served, queue is empty. Closing all client connections and shutting down." << endl;
            for (int sock : active_client_sockets) {
                close(sock);
            }

            server_running = false;  // Set server running to false
            close(server_socket);    // Close server socket
            pthread_cond_broadcast(&queue_cond);  // Signal all waiting threads to exit
        }
        pthread_mutex_unlock(&queue_mutex);
        this_thread::sleep_for(chrono::seconds(1));  // Monitor every 5 seconds
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

    // Read and process input file
    ifstream file(input_file);
    stringstream buffer;
    buffer << file.rdbuf();
    splitWordsFromFile(buffer.str());

    // Create server socket
    server_socket = socket(PF_INET, SOCK_STREAM, 0);
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

    // Bind and listen
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

    // Create single worker thread
    pthread_t worker_thread;
    if (pthread_create(&worker_thread, NULL, workerThread, NULL) != 0) {
        cerr << "Failed to create worker thread" << endl;
        return -1;
    }

    // Start monitoring the queue
    thread monitor_thread(monitorQueue);

    // Main server loop
    while (server_running) {
        sockaddr_in client_addr;
        socklen_t client_size = sizeof(client_addr);
        int* client_socket = new int(accept(server_socket, (struct sockaddr*)&client_addr, &client_size));
        active_client_sockets.push_back(*client_socket);

        if (*client_socket == -1) {
            delete client_socket;
            if (!server_running) break;  // Server is shutting down
            cerr << "Accept failed" << endl;
            continue;
        }

        // Create a new thread for each client
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
