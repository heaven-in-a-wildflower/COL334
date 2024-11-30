from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time, re, os
import sys
import hashlib
import subprocess 
import matplotlib.pyplot as plt

class DumbbellTopo(Topo):    
    def build(self, delay_sw2_s2='50ms'):
        # Create hosts
        c1 = self.addHost('c1')
        c2 = self.addHost('c2')
        s1 = self.addHost('s1')
        s2 = self.addHost('s2')

        # Create switches
        sw1 = self.addSwitch('sw1')
        sw2 = self.addSwitch('sw2')

        # Add links with specified parameters
        # Links between clients/servers and switches
        self.addLink(c1, sw1, delay='5ms')
        self.addLink(c2, sw1, delay='5ms')
        self.addLink(s1, sw2, delay='5ms')

        buffer_size = 500
        # Link between sw1 and sw2 (bottleneck link)
        self.addLink(sw1, sw2, bw=100, delay='5ms', max_queue_size=buffer_size)
        
        print("delay is ", delay_sw2_s2)
        # Link between sw2 and s2 with specified latency
        self.addLink(s2, sw2, delay=delay_sw2_s2)

def jain_fairness_index(allocations):
    n = len(allocations)
    sum_of_allocations = sum(allocations)
    sum_of_squares = sum(x ** 2 for x in allocations)
    
    jfi = (sum_of_allocations ** 2) / (n * sum_of_squares)
    return jfi

def plot_jfi_vs_latency():
    # Initialize lists to hold data
    delays = []
    jfi_values = []

    # Read data from the CSV file
    with open('p2_fairness.csv', 'r') as f:
        next(f)  # Skip header
        for line in f:
            parts = line.strip().split(',')
            delay = int(parts[0])
            jfi = float(parts[5])
            delays.append(delay)
            jfi_values.append(jfi)

    # Plot JFI vs Link Latency
    plt.figure()
    plt.plot(delays, jfi_values, marker='o', linestyle='-')
    plt.xlabel('Link Latency (ms)')
    plt.ylabel('Jain\'s Fairness Index (JFI)')
    plt.title('Jain\'s Fairness Index vs Link Latency')
    plt.grid(True)
    plt.savefig('jfi_vs_latency.png')
    plt.show()

def compute_md5(file_path):
    """Compute the MD5 hash of a file."""
    hasher = hashlib.md5()
    try:

        with open(file_path, 'rb') as file:
            # Read the file in chunks to avoid using too much memory for large files
            while chunk := file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None

def run():
    # Set the log level to info to see detailed output
    setLogLevel('info')
    
    # IP and port of the remote controller
    controller_ip = '127.0.0.1'  # Change to the controller's IP address if not local
    controller_port = 6653       # Default OpenFlow controller port
    
    # Output file 
    output_file = f'p2_fairness.csv'
    f_out = open(output_file, 'w')
    f_out.write("delay,md5_hash_1,md5_hash_2,ttc1,ttc2,jfi\n")


    SERVER_IP1 = "10.0.0.3"
    SERVER_PORT1 = 6555
    SERVER_IP2 = "10.0.0.4"
    SERVER_PORT2 = 6556
            
    NUM_ITERATIONS = 2
    OUTFILE = 'received_file.txt'
    
    delay_list = [x for x in range(0, 101, 20)]
    # delay_list = [100]
    # Loop to create the topology 10 times with varying loss (1% to 10%)
    for DELAY in delay_list:
        idx=0
        while idx<NUM_ITERATIONS:
            os.system("mn -c")
            print(f"\n--- Running topology with {DELAY}ms delay --")
            print(DELAY)
            # Create the custom topology with the specified loss
            topo = DumbbellTopo(delay_sw2_s2=f"{DELAY}ms")

            # Initialize the network with the custom topology and TCLink for link configuration
            net = Mininet(topo=topo, link=TCLink, controller=None)
            # Add the remote controller to the network
            remote_controller = RemoteController('c0', ip=controller_ip, port=controller_port)
            net.addController(remote_controller)

            # Start the network
            net.start()
            #CLI(net)
            # Get references to h1 and h2
            c1 = net.get('c1')
            c2 = net.get('c2')
            s1 = net.get('s1')
            s2 = net.get('s2')
            
            pref_c1 = "1"
            pref_c2 = "2"
            s1_cmd = f"python3 p2_server.py {SERVER_IP1} {SERVER_PORT1} > ./server1_output.log 2>&1 &"
            s2_cmd = f"python3 p2_server.py {SERVER_IP2} {SERVER_PORT2} > ./server2_output.log 2>&1 &"
            c1_cmd = f"python3 p2_client.py {SERVER_IP1} {SERVER_PORT1} --pref_outfile {pref_c1} > ./client1_output.log 2>&1 &"
            c2_cmd = f"python3 p2_client.py {SERVER_IP2} {SERVER_PORT2} --pref_outfile {pref_c2} > ./client2_output.log 2>&1 &"

            s1_pid = s1.cmd(s1_cmd)
            s2_pid = s2.cmd(s2_cmd)
            time.sleep(1)
            
            start_time_c1 = time.time()
            c1_pid = ""
            c2_pid = ""

            # while True:
            #     c1_pid_raw = c1.cmd(c1_cmd).strip()
            #     if not c1_pid_raw:
            #         continue
            #     else:
            #         c1_pid = c1_pid_raw.split()[-1]
            #         print(f"started client 1 with PID: {c1_pid}")
            #         break
            
            # start_time_c2 = time.time()

            # while True:
            #     c2_pid_raw = c2.cmd(c2_cmd).strip()
            #     if not c2_pid_raw:
            #         continue
            #     else:
            #         c2_pid = c2_pid_raw.split()[-1]
            #         print(f"started client 2 with PID: {c2_pid}")
            #         break

            # Start the clients only once

            c1_pid_raw = c1.cmd(c1_cmd).strip()
            if c1_pid_raw:
                c1_pid = c1_pid_raw.split()[-1]
                print(f"Started client 1 with PID: {c1_pid}")
            else:
                print("Failed to start client 1")
                continue

            start_time_c2 = time.time()
            c2_pid_raw = c2.cmd(c2_cmd).strip()
            if c2_pid_raw:
                c2_pid = c2_pid_raw.split()[-1]
                print(f"Started client 2 with PID: {c2_pid}")
            else:
                print("Failed to start client 2")
                continue
            
            #CLI(net)
            end_time_c1 = None
            end_time_c2 = None
            # Polling loop to check when each process completes
            while end_time_c1 is None or end_time_c2 is None:
                # Check if process for c1 has completed
                if end_time_c1 is None:
                    result_c1 = c1.cmd(f'ps')
                    if not result_c1 or str(c1_pid) not in result_c1:  # Process is no longer running
                        end_time_c1 = time.time()

                if end_time_c2 is None:
                    result_c2 = c2.cmd(f'ps')
                    if not result_c2 or str(c2_pid) not in result_c2:  # Process is no longer running
                        end_time_c2 = time.time()
           

            # Stop the network
            net.stop()
                
            # calculate metrics
            dur_c1 = end_time_c1 - start_time_c1
            dur_c2 = end_time_c2 - start_time_c2
            
            jfi = jain_fairness_index([1/dur_c1, 1/dur_c2])
            
            print(dur_c1, dur_c2, jfi) 
            # calculate md5 hash
            hash1 = compute_md5(f"{pref_c1}received_file.txt")
            hash2 = compute_md5(f"{pref_c2}received_file.txt")


            f_out.write(f"{DELAY},{hash1},{hash2},{dur_c1},{dur_c2},{jfi}\n")
            # Wait a moment before starting the next iteration

            idx+=1
    
    time.sleep(1)
    f_out.close()
    print("\n--- Completed all tests ---")


if __name__ == "__main__":
    run()
    # Plot JFI vs latency
    plot_jfi_vs_latency()