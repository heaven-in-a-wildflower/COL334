#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <cstring>
#include <fstream>
#include <thread>
#include <map>
#include "json.hpp"

using namespace std;
using json = nlohmann::json;

struct Info {
    string server_ip;
    int server_port;
    int client_id;
    int k;
    int p;
};

void logMessage(const string& message, int client_id) {
    ofstream log_file("client_" + to_string(client_id) + "_log.txt", ios::app);
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    
    auto microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()).count() % 1000000;

    log_file << "[" << put_time(localtime(&now_time_t), "%Y-%m-%d %H:%M:%S") << "." 
             << setw(6) << setfill('0') << microseconds << "] " 
             << message << endl;
}

void* countWords(void* arg) {
    Info* info = (Info*)arg;
    string server_ip = info->server_ip;
    int server_port = info->server_port;
    int k = info->k;
    int p = info->p;
    int client_id = info->client_id;

    int client_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (client_socket == -1) {
        logMessage("Error creating socket for client", client_id);
        return nullptr;
    }

    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr);

    const int max_retries = 50;         // Maximum number of retries
    const int retry_delay_ms = 1000;    // Delay between retries in milliseconds

    int attempt = 0;
    while (attempt < max_retries) {
        // Try to connect the client
        if (connect(client_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
            logMessage("Client " + to_string(client_id) + " failed to connect. Attempt " 
                        + to_string(attempt + 1) + " of " + to_string(max_retries), client_id);

            // Close the current socket
            close(client_socket);

            // Increment the attempt counter
            if (++attempt >= max_retries) {
                logMessage("Client " + to_string(client_id) + " failed to connect after " 
                            + to_string(max_retries) + " attempts.", client_id);
                return nullptr; // Return or handle the error as needed
            }

            // Wait before retrying
            this_thread::sleep_for(chrono::milliseconds(retry_delay_ms));

            // Create a new socket for the next attempt
            client_socket = socket(PF_INET, SOCK_STREAM, 0);
            if (client_socket == -1) {
                logMessage("Client " + to_string(client_id) + " failed to create a new socket on attempt " 
                            + to_string(attempt + 1), client_id);
                return nullptr; // Return or handle the error as needed
            }
        } else {
            logMessage("Client " + to_string(client_id) + " connected successfully on attempt " 
                        + to_string(attempt + 1), client_id);
            break; // Connection successful, exit the loop
        }
    }


    logMessage("Client connected to server", client_id);

    map<string, int> word_count;
    int offset = 0;
    char buffer[1024];
    auto start_time = chrono::high_resolution_clock::now();

    while (true) {
        string request = to_string(offset) + "\n";
        send(client_socket, request.c_str(), request.length(), 0);
        logMessage("Sent request: " + request, client_id);

        int words_received = 0;
        while (words_received < k) {
            memset(buffer, 0, sizeof(buffer));
            int ret = recv(client_socket, buffer, sizeof(buffer), 0);
            if (ret <= 0) {
                logMessage("Connection closed or error occurred", client_id);
                close(client_socket);
                return nullptr;
            }

            string response(buffer);
            logMessage("Received response: " + response, client_id);

            if (response == "$$\n") {
                logMessage("Invalid offset", client_id);
                close(client_socket);
                return nullptr;
            }

            string word;
            for (char ch : response) {
                if (ch == ',' || ch == '\n'){
                    if (word.empty()){
                        continue;
                    }
                    if (word == "EOF"){
                        auto end_time = chrono::high_resolution_clock::now();
                        chrono::duration<double> duration = end_time - start_time;
                        ofstream time_file("time_"+to_string(client_id)+".txt");
                        time_file << "Time duration: " << duration.count() << " seconds" << endl;
                        time_file.close();

                        ofstream outfile("output_" + to_string(client_id) + ".txt");
                        for (const auto& entry : word_count) {
                            outfile << entry.first << ", " << entry.second << endl;
                        }
                        outfile.close();
                        logMessage("EOF received, closing connection", client_id);
                        close(client_socket);

                        return nullptr;
                    }
                    word_count[word]++;
                    words_received++;
                    word.clear();
                }
                else{
                    word += ch;
                }
            }
        }
        offset += k;
    }
}

int main(){
    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int k = config["k"];
    int p = config["p"];
    int num_clients = config["num_clients"];

    pthread_t clients[num_clients];
    Info client_data[num_clients];

    for (int i = 0; i < num_clients; ++i) {
        client_data[i].client_id = i + 1;
        client_data[i].server_ip = server_ip;
        client_data[i].server_port = server_port;
        client_data[i].k = k;
        client_data[i].p = p;

        pthread_create(&clients[i], nullptr, countWords, &client_data[i]);
    }

    for (int i = 0; i < num_clients; ++i) {
        pthread_join(clients[i], nullptr);
    }

    return 0;
}
