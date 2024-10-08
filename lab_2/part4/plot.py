import json
import subprocess
import time
import os
import numpy as np
import matplotlib.pyplot as plt

# Load configuration
with open('config.json') as f:
    config = json.load(f)

server_ip = config['server_ip']
server_port = config['server_port']
filename = config['input_file']
k = config['k']
p = 1
num_clients = list(range(1, 32, 4))
num_runs = 10

def run_experiment(num_client, num_runs, server_bin, client_bin):
    # Initialize a list to store completion times for each client
    times = [[] for _ in range(num_client)]

    for run_num in range(1, num_runs + 1):
        print(f"--- Run {run_num} ---")
        
        # Ensure previous server is killed
        subprocess.call(['pkill', '-9', 'server'])
        subprocess.call(['pkill', '-9', 'server_rr'])
        time.sleep(1)
        
        # Start the server
        server_proc = subprocess.Popen([f'./{server_bin}'])
        print(f"{server_bin} started.")

        # Wait for the server to initialize
        time.sleep(0.05)

        # Start the client
        client_proc = subprocess.Popen([f'./{client_bin}'], stdout=subprocess.PIPE)
        client_proc.communicate()
        print(f"{client_bin} finished.")

        # For each client, read their respective log file and extract the completion time
        for i in range(1, num_client + 1):
            log_file_path = f'time_{i}.txt'
            
            # Check if log file exists
            if os.path.exists(log_file_path):
                with open(log_file_path, 'r') as log_file:
                    time_line = log_file.readline().strip()
                    times[i-1].append(float(time_line)/1000)
                    print(float(time_line)/1000)
            else:
                print(f"Log file for client {i} not found.")
        
        # Kill the server after this run
        print(f"Terminating {server_bin}.")
        server_proc.terminate()
        server_proc.wait()  # Ensure the server has terminated properly
        print(f"{server_bin} terminated.")
    
    # Calculate the average completion time for each client
    client_averages = [sum(client_times) / len(client_times) for client_times in times if client_times]
    
    # Calculate the overall average completion time for all clients
    overall_average = sum(client_averages) / len(client_averages) if client_averages else 0

    print(f"Overall average completion time: {overall_average} ms")
    return overall_average

# Function to run experiments for different server-client pairs
def run_all_experiments(num_clients, num_runs):
    experiment_labels = ['FIFO', 'RR']
    servers = ['server', 'server_rr']
    clients = ['client', 'client']

    results = {label: [] for label in experiment_labels}

    for num_client in num_clients:
        print(f"Running experiment for n = {num_client}")

        for label, server, client in zip(experiment_labels, servers, clients):
            print(f"Running {label} experiment")
            config['num_clients'] = num_client
            with open('config.json', 'w') as f:
                json.dump(config, f)

            # Run the experiment for this number of clients and this setup
            avg_completion_time = run_experiment(num_client, num_runs, server, client)
            results[label].append(avg_completion_time)

    return results

# Run the experiments and collect results
experiment_results = run_all_experiments(num_clients, num_runs)

# Plot the results
plt.figure(figsize=(10, 6))
for label, times in experiment_results.items():
    plt.plot(num_clients, times, '-o', label=f'Avg Completion Time ({label})')

plt.xlabel('n (Number of clients)')
plt.ylabel('Average Completion Time (ms)')
plt.title('Completion Time vs. Number of clients served (n)')
plt.legend()
plt.grid(True)
plt.savefig('plot.png')

with open('results.json', 'w') as f:
    json.dump(experiment_results, f)
