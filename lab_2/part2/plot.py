import json
import subprocess
import time
import os
import numpy as np
import matplotlib.pyplot as plt

with open('config.json') as f:
    config = json.load(f)

server_ip = config['server_ip']
server_port = config['server_port']
filename = config['input_file']
k = config['k']
p = config['p']
num_clients = list(range(1, 33, 4))
num_runs = 5

def run_experiment(num_client, num_runs):
    times = [[] for _ in range(num_client)]

    for run_num in range(1, num_runs + 1):
        print(f"--- Run {run_num} ---")
        
        # subprocess.call(['pkill', '-9', 'server'])
        subprocess.call(['rm', '-f', '*log.txt'])
        subprocess.call(['rm', '-f', 'time*.txt'])
        # time.sleep(1)
        
        server_proc = subprocess.Popen(['./server'])
        print("Server started.")

        # Wait for the server to initialize
        time.sleep(0.05)

        client_proc = subprocess.Popen(['./client'], stdout=subprocess.PIPE)
        client_proc.communicate()
        print("Client finished.")

        for i in range(1, num_client + 1):
            log_file_path = f'time_{i}.txt'

            if os.path.exists(log_file_path):
                with open(log_file_path, 'r') as time_file:
                    time_line = time_file.readline().strip().split()[2]
                    times[i-1].append(float(time_line)*1000)
            else:
                print(f"Log file for client {i} not found.")
        
        print("Terminating server.")
        server_proc.terminate()
        server_proc.wait()
        print("Server terminated.")
    
    # Calculate the average completion time for each client
    client_averages = [sum(client_times) / len(client_times) for client_times in times if client_times]
    
    # Calculate the overall average completion time for all clients
    overall_average = sum(client_averages) / len(client_averages) if client_averages else 0

    print(f"Overall average completion time: {overall_average} ms")
    return overall_average


# Run the experiment and collect results
results = []
for num_client in num_clients:
    print(f"Running experiment for n = {num_client}")
    config['num_clients'] = num_client
    with open('config.json', 'w') as f:
        json.dump(config, f)

    # Run the experiment for this number of clients and get the overall average
    avg_completion_time = run_experiment(num_client, num_runs)
    results.append(avg_completion_time)

# Plot the results
plt.plot(num_clients, results, '-o', label='Average Completion Time')
plt.xlabel('n (Number of clients)')
plt.ylabel('Average Completion Time (ms)')
plt.title('Completion Time vs. Number of clients served(n)')
plt.legend()
plt.savefig('plot.png')

with open('results.json', 'w') as f:
    json.dump(dict(zip(num_clients, results)), f)