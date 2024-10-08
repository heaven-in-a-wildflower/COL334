#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <fstream>
#include <thread>
#include <map>
#include <atomic>
#include "json.hpp"
#include <mutex>
#include <condition_variable>

using namespace std;
using json = nlohmann::json;

struct Info {
    string server_ip;
    int server_port;
    int client_id;
    int k;
};

struct RogueInfo {
    int client_socket;
    int k;
    int thread_id;
    atomic<int>* off;
    atomic<bool>* done;
    atomic<int>* words;
};

atomic<bool> ready_to_send[5]; // Array to track if each sending thread is ready

void logMessage(const string& message, int client_id) {
    ofstream log_file("client_" + to_string(client_id) + "_log.txt", ios::app);
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    
    auto microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()).count() % 1000000;

    log_file << "[" << put_time(localtime(&now_time_t), "%Y-%m-%d %H:%M:%S") << "." 
             << setw(6) << setfill('0') << microseconds << "] " 
             << message << endl;
    return;
}

// Helper function for word frequency counting for normal clients
void* countWords(void* arg) {
    Info* info = (Info*)arg;
    string server_ip = info->server_ip;
    int server_port = info->server_port;
    int k = info->k;
    int client_id = info->client_id;

    int client_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (client_socket == -1) {
        logMessage("Error creating socket for client " + to_string(client_id), client_id);
        return nullptr;
    }

    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr);

    const int max_retries = 50;         
    const int retry_delay_ms = 1000;    

    int attempt = 0;
    while (attempt < max_retries) {
        if (connect(client_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
            logMessage("Client " + to_string(client_id) + " failed to connect. Attempt " 
                        + to_string(attempt + 1) + " of " + to_string(max_retries), client_id);

            if (++attempt >= max_retries) {
                logMessage("Client " + to_string(client_id) + " failed to connect after " 
                            + to_string(max_retries) + " attempts.", client_id);
                return nullptr;
            }
            this_thread::sleep_for(chrono::milliseconds(retry_delay_ms));
        } else {
            logMessage("Client " + to_string(client_id) + " connected successfully on attempt " 
                        + to_string(attempt + 1), client_id);
            break;
        }
    }

    std::chrono::steady_clock::time_point begini = std::chrono::steady_clock::now();

    map<string, int> word_count;
    int offset = 0;
    char buffer[1024];

    while (true) {
        string request = to_string(offset) + "\n";
        logMessage("Sending to server: " + request, client_id);
        send(client_socket, request.c_str(), request.length(), 0);

        int words_received = 0;
        while (words_received < k) {
            memset(buffer, 0, sizeof(buffer));
            int ret = recv(client_socket, buffer, sizeof(buffer), 0);
            logMessage("Received from server: " + string(buffer), client_id);

            if (ret <= 0) {
                close(client_socket);
                return nullptr;
            }

            string response(buffer);
            if (response == "$$\n") {
                close(client_socket);
                return nullptr;
            }

            string word;
            for (char ch : response) {
                if (ch == ',' || ch == '\n') {
                    if (word.empty()) continue;
                    if (word == "EOF") {
                        ofstream outfile("output_" + to_string(client_id) + ".txt");
                        for (const auto& entry : word_count) {
                            outfile << entry.first << ", " << entry.second << endl;
                        }
                        outfile.close();
                        close(client_socket);

                        std::chrono::steady_clock::time_point endi = std::chrono::steady_clock::now();
                        ofstream timefile("time_" + to_string(client_id) + ".txt");
                        timefile << chrono::duration_cast<std::chrono::microseconds>(endi - begini).count();

                        return nullptr;
                    }
                    word_count[word]++;
                    words_received++;
                    word.clear();
                } else {
                    word += ch;
                }
            }
        }
        offset += k;
    }
}

std::chrono::steady_clock::time_point begin_time;

// Helper function for rogue sending requests
void* rogueRequest(void* arg) {
    RogueInfo* info = (RogueInfo*)arg;
    int client_socket = info->client_socket;
    int k = info->k;
    atomic<int>* offset = info->off;
    atomic<int>* words = info->words;
    atomic<bool>* done = info->done;
    int thread_id = info->thread_id;

    while (true) {
        // Check if this thread is ready to send
        if (ready_to_send[thread_id].load()) {
            string request = to_string(offset->fetch_add(k)) + "\n";
            logMessage("Sending to server: " + request, 1);

            // Attempt to send the request without locking
            if (send(client_socket, request.c_str(), request.length(), 0) == -1) {
                logMessage("Uh-oh! Client socket closed. Time to bounce", 1);
                close(client_socket);
                return nullptr;
            }

            ready_to_send[thread_id] = false; // Reset send status for this thread
        }
        else if (*done){
            break;
        }
        usleep(10);
        // Sleep or yield to prevent busy-waiting
        // this_thread::yield(); // Yielding can be adjusted based on your requirements
    }

    return nullptr;
}

// Helper function for rogue receiving responses
void* rogueReceiver(void* arg) {
    RogueInfo* info = (RogueInfo*)arg;
    int client_socket = info->client_socket;
    int k = info->k;
    atomic<bool>* done = info->done;
    atomic<int>* words = info->words;

    map<string, int> thread_word_count;  // Map to store word counts
    char buffer[1024];
    int current_thread = 0;
    int words_received = 0;

    while (true) {
        memset(buffer, 0, sizeof(buffer));

        int ret = recv(client_socket, buffer, sizeof(buffer), 0);
        logMessage("Received from server: " + string(buffer), 1);  // Log server response

        if (ret <= 0) {
            logMessage("Socket closed or error occurred", 1);
            *done = true;
            break;
        }

        string response(buffer);
        if (response == "$$\n") {
            *done = true;
            logMessage("EOF received, ending requests.", 1);
            continue;
        }

        string word;
        for (char ch : response) {
            if (ch == ',' || ch == '\n') {
                if (!word.empty()) {
                    if (word == "EOF") {
                        *done = true;
                        logMessage("EOF received, ending requests.", 1);
                        std::chrono::steady_clock::time_point endtime = std::chrono::steady_clock::now();
                        ofstream timefile("time_1.txt");
                        timefile << chrono::duration_cast<std::chrono::microseconds>(endtime - begin_time).count();
                        continue;
                    }
                    thread_word_count[word]++;
                    words_received++;
                }
                word.clear();
            } else {
                word += ch;
            }
        }

        // *words += words_received;
        // logMessage("Words received in this iteration: " + to_string(words_received), 1);

        while (words_received >= k){
            ready_to_send[current_thread] = true;

            current_thread = (current_thread + 1) % 5;
            words_received -= k;
        }
    }

    ofstream outfile("output_rogue.txt");
    for (const auto& entry : thread_word_count) {
        outfile << entry.first << ", " << entry.second << endl;
    }
    outfile.close();

    return nullptr;
}

// Thread function for the rogue client with word counting
void* rogueClient(void* arg) {
    Info* info = (Info*)arg;
    string server_ip = info->server_ip;
    int server_port = info->server_port;
    int k = info->k;

    int client_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (client_socket == -1) {
        logMessage("Error creating socket for rogue client", 1);
        return nullptr;
    }

    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr);

    const int max_retries = 50;
    const int retry_delay_ms = 1000;
    int attempt = 0;

    while (attempt < max_retries) {
        if (connect(client_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
            logMessage("Rogue client failed to connect. Attempt " 
                        + to_string(attempt + 1) + " of " + to_string(max_retries), 1);

            if (++attempt >= max_retries) {
                logMessage("Rogue client failed after " + to_string(max_retries) + " attempts.", 1);
                return nullptr;
            }
            this_thread::sleep_for(chrono::milliseconds(retry_delay_ms));
        } else {
            logMessage("Rogue client connected successfully on attempt " 
                        + to_string(attempt + 1), 1);
            break;
        }
    }

    begin_time = std::chrono::steady_clock::now();

    atomic<int> offset(0);
    atomic<int> words(0);
    atomic<bool> done(false);
    pthread_t send_threads[5], recv_thread;

    RogueInfo roguedata[5];
    for (int i = 0; i < 5; ++i) {
        roguedata[i].client_socket = client_socket;
        roguedata[i].off = &offset;
        roguedata[i].done = &done;
        roguedata[i].words = &words;
        roguedata[i].k = k;
        roguedata[i].thread_id = i;

        ready_to_send[i] = true;  // Initially, all threads are ready to send
        pthread_create(&send_threads[i], nullptr, rogueRequest, &roguedata[i]);
    }

    pthread_create(&recv_thread, nullptr, rogueReceiver, &roguedata);

    for (int i = 0; i < 5; ++i) {
        pthread_join(send_threads[i], nullptr);
    }
    pthread_join(recv_thread, nullptr);

    close(client_socket);

    return nullptr;
}

int main() {
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int k = 10;
    int num_clients = config["num_clients"];

    pthread_t clients[num_clients];
    Info client_data[num_clients];

    for (int i = 0; i < num_clients; ++i) {
        client_data[i].client_id = i + 1;
        client_data[i].server_ip = server_ip;
        client_data[i].server_port = server_port;
        client_data[i].k = k;

        if (i == 0) {
            pthread_create(&clients[i], nullptr, rogueClient, &client_data[i]);
        } else {
            pthread_create(&clients[i], nullptr, countWords, &client_data[i]);
        }
    }

    for (int i = 0; i < num_clients; ++i) {
        pthread_join(clients[i], nullptr);
    }

    return 0;
}
