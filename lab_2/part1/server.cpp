#include <iostream>
#include <fstream>
#include <sstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstring>
#include <arpa/inet.h>
#include "json.hpp"
#include <chrono>
#include <iomanip>

using namespace std;

using json = nlohmann::json;
vector<string> word_list;
ofstream log_file;

// Function to log messages with timestamps
void logMessage(const string& message) {
    auto now = chrono::system_clock::now();
    auto now_time_t = chrono::system_clock::to_time_t(now);
    
    // Get microseconds since epoch
    auto microseconds = chrono::duration_cast<chrono::microseconds>(now.time_since_epoch()).count() % 1000000;

    log_file << "[" << put_time(localtime(&now_time_t), "%Y-%m-%d %H:%M:%S") << "." 
             << setw(6) << setfill('0') << microseconds << "] " 
             << message << endl;
}

void splitWordsFromFile(const string& input) {
    istringstream stream(input);
    string word;
    while (getline(stream, word, ',')) {
        word_list.push_back(word);
    }
}

bool handleClient(int client_socket, int k, int p) {
    char buffer[1024];
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int ret = recv(client_socket, buffer, sizeof(buffer), 0);
        if (ret <= 0) {
            close(client_socket);
            return 0;
        }

        string request(buffer);
        int offset = stoi(request);

        if (offset >= word_list.size()) {
            send(client_socket, "$$\n", 3, 0);
            close(client_socket);
            return 1;
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
            logMessage("Packet: " + pkt);
            send(client_socket, pkt.c_str(), pkt.length(), 0);
        }

        if (offset + words_sent >= word_list.size()) {
            close(client_socket);
            return 1;
        }
    }
    return 0;
}

int main() {
    log_file.open("server_log.txt", ios::app);
    if (!log_file.is_open()) {
        cerr << "Failed to open log file." << endl;
        return -1;
    }

    ifstream config_file("config.json");
    json config;
    config_file >> config;

    string server_ip = config["server_ip"];
    int server_port = config["server_port"];
    int k = config["k"];
    int p = config["p"];
    string input_file = config["input_file"];

    ifstream file(input_file);
    stringstream buffer;
    buffer << file.rdbuf();
    splitWordsFromFile(buffer.str());

    int server_socket = socket(PF_INET, SOCK_STREAM, 0);
    if (server_socket == -1) {
        logMessage("Error creating socket: " + string(strerror(errno)));
        return -1;
    }

    int optval = 1;
    if (setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval)) == -1) {
        logMessage("Failed to set SO_REUSEADDR: " + string(strerror(errno)));
        close(server_socket);
        return -1;
    }

    sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(server_port);
    
    if (inet_pton(AF_INET, server_ip.c_str(), &server_addr.sin_addr) <= 0) {
        logMessage("Invalid IP address: " + server_ip);
        close(server_socket);
        return -1;
    }

    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == -1) {
        logMessage("Bind failed: " + string(strerror(errno)));
        close(server_socket);
        return -1;
    }

    if (listen(server_socket, 10) == -1) {
        logMessage("Listen failed: " + string(strerror(errno)));
        close(server_socket);
        return -1;
    }

    logMessage("Server listening on " + server_ip + ":" + to_string(server_port));

    while (true) {
        sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_len);

        if (client_socket == -1) {
            logMessage("Failed to accept connection");
            continue;
        }

        bool done = handleClient(client_socket, k, p);
        if (done) break;
    }

    close(server_socket);
    log_file.close();
    return 0;
}
