#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <fstream>
#include <map>
#include <chrono>
#include "json.hpp"

using namespace std;
using json = nlohmann::json;

void logMessage(const string& message) {
    ofstream log_file("client_log.txt", ios::app);
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    
    // Get microseconds since epoch
    auto microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()).count() % 1000000;

    log_file << "[" << put_time(localtime(&now_time_t), "%Y-%m-%d %H:%M:%S") << "." 
             << setw(6) << setfill('0') << microseconds << "] " 
             << message << endl;
}

void countWords(const string& server_ip, int server_port, int k, int p) {
    int client_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (client_socket == -1) {
        logMessage("Error creating socket for client");
        return;
    }

    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr);

    if (connect(client_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
        logMessage("Client failed to connect");
        close(client_socket);
        return;
    }

    logMessage("Client connected to server");

    map<string, int> word_count;
    int offset = 0;
    char buffer[1024];

    auto start_time = chrono::high_resolution_clock::now();

    while (true) {
        string request = to_string(offset) + "\n";
        send(client_socket, request.c_str(), request.length(), 0);
        logMessage("Sent request: " + request);

        int words_received = 0;
        while (words_received < k) {
            memset(buffer, 0, sizeof(buffer));
            int ret = recv(client_socket, buffer, sizeof(buffer), 0);
            if (ret <= 0) {
                logMessage("Connection closed or error occurred");
                close(client_socket);
                return;
            }

            string response(buffer);
            logMessage("Received response: " + response);

            if (response == "$$\n"){
                logMessage("Invalid offset");
                close(client_socket);
                break;
            }

            string word;
            for (char ch : response) {
                if (ch == ',' || ch == '\n') {
                    if (word.empty()) {
                        continue;
                    }
                    if (word == "EOF") {
                        auto end_time = chrono::high_resolution_clock::now();
                        chrono::duration<double> duration = end_time - start_time;
                        ofstream time_file("time.txt");
                        time_file << "Time duration: " << duration.count() << " seconds" << endl;
                        time_file.close();
                        ofstream outfile("output.txt");
                        for (const auto& entry : word_count) {
                            outfile << entry.first << ", " << entry.second << endl;
                        }
                        outfile.close();
                        logMessage("EOF received, closing connection");
                        close(client_socket);
                        return;
                    }
                    word_count[word]++;
                    words_received++;
                    word.clear();
                }
                else {
                    word += ch;
                }
            }
        }
        offset += k;
    }
}

int main() {
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int k = config["k"];
    int p = config["p"];

    countWords(server_ip, server_port, k, p);
    return 0;
}
