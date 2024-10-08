import json
import subprocess
import numpy as np
import matplotlib.pyplot as plt
import time

# Load configuration
with open('config.json') as f:
    config = json.load(f)

server_ip = config['server_ip']
server_port = config['server_port']
filename = config['input_file']
k = config['k']
p_values = list(range(1, 11))
num_runs = 10

# Function to run the client and server
def run_experiment(p):
    times = []
    for _ in range(num_runs):
        server_proc = subprocess.Popen(['./server'])

        time.sleep(0.05)

        client_proc = subprocess.Popen(['./client'], stdout=subprocess.PIPE)
        client_proc.communicate()

        with open('time.txt', 'r') as time_file:
            time_line = time_file.readline().strip().split()[2]
            times.append(float(time_line)*1000)

        # Kill the server
        server_proc.terminate()

    return times

# Run the experiment and collect results
results = {}
for p in p_values:
    print(f"Running experiment for p = {p}")
    config['p'] = p
    with open('config.json', 'w') as f:
        json.dump(config, f)

    completion_times = run_experiment(p)
    results[p] = completion_times

# Plot the results
means = [np.mean(results[p]) for p in p_values]
std_devs = [np.std(results[p]) for p in p_values]

plt.errorbar(p_values, means, yerr=std_devs, fmt='-o', capsize=5, label='Completion Time')
plt.xlabel('p (words per packet)')
plt.ylabel('Average Completion Time (ms)')
plt.title('Completion Time vs. Number of Words per Packet (p)')
plt.legend()
plt.savefig('plot.png')
# plt.show()

# Optionally, save the raw data
with open('results.json', 'w') as f:
    json.dump(results, f)
