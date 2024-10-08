#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <fstream>
#include <thread>
#include <map>
#include <random>
#include "json.hpp"

using namespace std;
using json = nlohmann::json;

struct Info{
    string server_ip;
    int server_port;
    int client_id;
    int T;
    double p;
};

void logMessage(const string& message, int client_id) {
    ofstream log_file("client_beb_" + to_string(client_id) + "_log.txt", ios::app);
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    
    auto microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()).count() % 1000000;

    log_file << "[" << put_time(localtime(&now_time_t), "%Y-%m-%d %H:%M:%S") << "." 
             << setw(6) << setfill('0') << microseconds << "] " 
             << message << endl;
}

double generate_random(int k){
    random_device rd;
    mt19937 gen(rd());
    uniform_int_distribution<> dis(0, (1 << min(k, 10)) - 1);
    return dis(gen);
}

void* countWords(void* arg) {
    Info* info = (Info*)arg;
    string server_ip = info->server_ip;
    int server_port = info->server_port;
    int T = info->T;
    double p = info->p;
    int k = 10;
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

    if (connect(client_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
        logMessage("Client " + to_string(client_id) + " failed to connect", client_id);
        close(client_socket);
        return nullptr;
    }

    map<string, int> word_count;
    vector<string> this_slot_words;
    int offset = 0;
    char buffer[1024];

    int num_collisions = 0;

    // Start measuring time 
    std::chrono::steady_clock::time_point begin = std::chrono::steady_clock::now();

    while (true) {
        string request = to_string(offset) + "\n";
        send(client_socket, request.c_str(), request.length(), 0);
        logMessage("Client " + to_string(client_id) + " sent request: " + request, client_id);

        int words_received = 0;
        while (words_received < k) {
            memset(buffer, 0, sizeof(buffer));
            int ret = recv(client_socket, buffer, sizeof(buffer), 0);
            if (ret <= 0) {
                logMessage("Connection closed or error occurred for client " + to_string(client_id), client_id);
                close(client_socket);
                return nullptr;
            }

            string response(buffer);
            if (response == "$$\n") {
                logMessage("Invalid response received for client " + to_string(client_id), client_id);
                close(client_socket);
                return nullptr;
            }

            string word;
            for (char ch : response) {
                if (ch == ',' || ch == '\n') {
                    if (word.empty()){
                        continue;
                    }
                    if (word == "EOF") {
                        for (auto x : this_slot_words){
                            word_count[x]++;
                            words_received++;
                        }

                        // End measuring time
                        std::chrono::steady_clock::time_point end = std::chrono::steady_clock::now();
                        ofstream timefile("time_" + to_string(client_id) + ".txt");
                        timefile << "Completion time = " << std::chrono::duration_cast<std::chrono::microseconds>(end - begin).count() << "[µs]" << std::endl;

                        ofstream outfile("output_" + to_string(client_id) + ".txt");
                        for (const auto& entry : word_count) {
                            outfile << entry.first << ", " << entry.second << endl;
                        }
                        outfile.close();
                        logMessage("Client " + to_string(client_id) + " received EOF, closing connection", client_id);
                        close(client_socket);
                        return nullptr;
                    }
                    if (word == "HUH!") {
                        words_received = k;
                        offset -= k;
                        this_slot_words.clear();
                        num_collisions++;
                        logMessage("Collision occurred for client " + to_string(client_id) + ", number of collisions: " + to_string(num_collisions), client_id);
                        usleep(generate_random(num_collisions) * T * 1000);
                        break;
                    }
                    this_slot_words.push_back(word);
                    word.clear();
                }
                else {
                    word += ch;
                }
            }
            if (word != "HUH!" && this_slot_words.size() == k) {
                for (auto x : this_slot_words){
                    word_count[x]++;
                    words_received++;
                }
                this_slot_words.clear();
                num_collisions = 0;
            }
        }
        offset += k;
    }
}

int main() {
    // Read config.json
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int T = config["T"];
    int num_clients = config["num_clients"];

    pthread_t clients[num_clients];
    Info client_data[num_clients];

    for (int i = 0; i < num_clients; ++i) {
        client_data[i].client_id = i + 1;
        client_data[i].server_ip = server_ip;
        client_data[i].server_port = server_port;
        client_data[i].T = T;
        client_data[i].p = 1.0 / num_clients;

        pthread_create(&clients[i], nullptr, countWords, &client_data[i]);
    }

    for (int i = 0; i < num_clients; ++i) {
        pthread_join(clients[i], nullptr);
    }

    return 0;
}
