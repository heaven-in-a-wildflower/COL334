import pyshark
from datetime import timedelta,datetime
from collections import defaultdict
import subprocess 
import argparse 
import matplotlib.pyplot as plt 

def run_tshark_command(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tshark command failed with error: {result.stderr}")
    return result.stdout

import subprocess

def write_tshark_output_to_file(pcap_file, client_ip, server_ip, output_file):
    # Define the tshark command
    command = [
        'tshark', '-r', pcap_file,
        '-Y', f'tcp && ip.src == {client_ip} && ip.dst == {server_ip}',
        '-T', 'fields', '-e', 'frame.time_relative', '-e', 'frame.len'
    ]
    
    # Execute the command and save the output to a file
    with open(output_file, 'w') as file:
        subprocess.run(command, text=True, stdout=file)

def find_ndt7_tls_handshakes(pcap_file):
    # Open the pcap file with a display filter for TLS Client Hello
    cap = pyshark.FileCapture(pcap_file, display_filter='tls.handshake.type == 1')
    
    # List to store packets with the desired SNI
    matching_packets = []
    
    for packet in cap:
        if 'TLS' in packet:
            try:
                if hasattr(packet.tls, 'handshake_extensions_server_name'):
                    sni = packet.tls.handshake_extensions_server_name
                    if sni.startswith('ndt-mlab'):
                        matching_packets.append(packet)
                        # print(f"  SNI: {sni}")
            except AttributeError:
                continue    
    handshake1 = None
    handshake2 = matching_packets[-1]
    for i in range(1, len(matching_packets)):
        prev_packet = matching_packets[i - 1]
        current_packet = matching_packets[i]
        
        time_diff = (current_packet.sniff_time - prev_packet.sniff_time).total_seconds()
        if time_diff > 5:
            handshake1 = prev_packet
            break  # Exit loop after finding the first valid pair

    if handshake1 and handshake2:
        print(f"Handshake 1:\n  Timestamp: {handshake1.sniff_time}\n  SNI: {handshake1.tls.handshake_extensions_server_name}")
        print(f"Handshake 2:\n  Timestamp: {handshake2.sniff_time}\n  SNI: {handshake2.tls.handshake_extensions_server_name}")
    else:
        print("No suitable handshake pairs found.")
    return handshake1, handshake2

def find_client_and_server_ips(handshake):
    client_ip = ''
    server_ip = ''
    if 'IP' in handshake:
        client_ip = handshake.ip.src
        server_ip = handshake.ip.dst
    elif 'IPv6' in handshake:
        client_ip = handshake.ipv6.src
        server_ip = handshake.ipv6.dst
    return client_ip,server_ip

def find_tcp_fin_packet(pcap_file, client_ip, server_ip):
    latest_packet = None
    # Open the pcap file
    cap = pyshark.FileCapture(pcap_file, display_filter='tcp.flags.fin == 1 ')
    try:
        for packet in cap:
            if 'IP' in packet:
                if packet.ip.src == server_ip and packet.ip.dst == client_ip:
                    return packet
            elif 'IPv6' in packet:
                if packet.ipv6.src == server_ip and packet.ipv6.dst == client_ip:
                    return packet
    finally:
        # Explicitly close the capture file
        cap.close()

    return latest_packet

def is_download_test(pcap_file, client_ip, server_ip, start_time, delta_t):
    # Open the pcap file
    end_time = start_time + timedelta(seconds=delta_t)
    cap = pyshark.FileCapture(pcap_file,display_filter = f'tcp && frame.time >= "{start_time}" && frame.time <= "{end_time}"')
    server_to_client_traffic = 0
    client_to_server_traffic = 0

    for packet in cap:
        src_ip = packet.ip.src if 'IP' in packet else packet.ipv6.src
        dst_ip = packet.ip.dst if 'IP' in packet else packet.ipv6.dst
        payload_length = int(packet.length)
        # Determine the direction of traffic
        if src_ip == client_ip and dst_ip == server_ip:
            client_to_server_traffic += payload_length
        elif src_ip == server_ip and dst_ip == client_ip:
            server_to_client_traffic += payload_length
        # print(f'S to C : {server_to_client_traffic}')
        # print(f'C to S : {client_to_server_traffic}')

    if server_to_client_traffic > client_to_server_traffic:
        return True 
    else:
        return False

def measure_throughput(pcap_file, client_ip, server_ip, start_time, end_time, direction):
    if direction == 'download':
        command = [
            'tshark', '-r', pcap_file,
            '-Y', f'tcp && frame.time >= "{start_time.strftime("%Y-%m-%d %H:%M:%S.%f")}" && frame.time <= "{end_time.strftime("%Y-%m-%d %H:%M:%S.%f")}" && ip.src == {server_ip} && ip.dst == {client_ip}',
            '-T', 'fields', '-e', 'frame.len'
        ]
    else:
        command = [
            'tshark', '-r', pcap_file,
            '-Y', f'tcp && frame.time >= "{start_time.strftime("%Y-%m-%d %H:%M:%S.%f")}" && frame.time <= "{end_time.strftime("%Y-%m-%d %H:%M:%S.%f")}" && ip.src == {client_ip} && ip.dst == {server_ip}',
            '-T', 'fields', '-e', 'frame.len'
        ]
    
    output = run_tshark_command(command)
    lengths = output.strip().split('\n')
    traffic = sum(int(length) for length in lengths if length.isdigit())
    
    time_taken = end_time - start_time
    time_taken_secs = time_taken.total_seconds()
    throughput = traffic / time_taken_secs
    throughput_mbps = (throughput * 8) / 1e6
    return throughput_mbps

def find_ndt7_test_traffic_fraction(pcap_file, client_ip, server_ip):
    command_server_to_client = [
        'tshark', '-r', pcap_file,
        '-Y', f'tcp && ip.src == {server_ip} && ip.dst == {client_ip}',
        '-T', 'fields', '-e', 'frame.len'
    ]
    
    command_client_to_server = [
        'tshark', '-r', pcap_file,
        '-Y', f'tcp && ip.src == {client_ip} && ip.dst == {server_ip}',
        '-T', 'fields', '-e', 'frame.len'
    ]
    
    command_total = [
        'tshark', '-r', pcap_file,
        '-T', 'fields', '-e', 'frame.len'
    ]
    
    output_server_to_client = run_tshark_command(command_server_to_client)
    output_client_to_server = run_tshark_command(command_client_to_server)
    output_total = run_tshark_command(command_total)
    
    server_to_client_traffic = sum(int(length) for length in output_server_to_client.splitlines() if length.isdigit())
    client_to_server_traffic = sum(int(length) for length in output_client_to_server.splitlines() if length.isdigit())
    total_traffic = sum(int(length) for length in output_total.splitlines() if length.isdigit())

    ndt7_test_traffic = server_to_client_traffic + client_to_server_traffic
    ndt7_traffic_fraction = ndt7_test_traffic / total_traffic
    
    return ndt7_traffic_fraction

def find_speeds(pcap_file,client_ip,server_ip,handshake1,handshake2,tcp_fin_packet,download_test_flag):
    if download_test_flag:
        print("Handshake 1 is the download handshake and Handshake 2 is the upload handshake.")
        download_throughput = measure_throughput(pcap_file, client_ip, server_ip, handshake1.sniff_time, handshake2.sniff_time,direction='download')
        print(f'Average Download throughput= {download_throughput} Mbps')

        upload_throughput = measure_throughput(pcap_file,client_ip,server_ip,handshake2.sniff_time,tcp_fin_packet.sniff_time,direction='upload')
        print(f'Average Upload throughput= {upload_throughput} Mbps')

    else:
        print("Handshake 1 is the upload handshake and Handshake 2 is the download handshake.")
        download_throughput = measure_throughput(pcap_file, client_ip, server_ip, handshake2.sniff_time, tcp_fin_packet.sniff_time, direction='download')
        print(f'Average Download throughput= {download_throughput} Mbps')

        upload_throughput = measure_throughput(pcap_file, client_ip, server_ip, handshake1.sniff_time, handshake2.sniff_time,direction='upload')
        print(f'Average Upload throughput= {upload_throughput} Mbps')

def process_data(file_path):
    """Processes data from a file to compute total bytes and packet counts per second."""
    bytes_per_second = defaultdict(int)
    packets_per_second = defaultdict(int)
    
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                timestamp, size = parts
                epoch_time = float(timestamp)
                second = int(epoch_time)
                bytes_per_second[second] += int(size)
                packets_per_second[second] += 1
    
    return bytes_per_second, packets_per_second

def plot_two_directions(bytes_client_to_server, bytes_server_to_client, packets_client_to_server, packets_server_to_client):
    """Plots total bytes and number of packets per second for both directions."""
    sorted_seconds_client_to_server = sorted(bytes_client_to_server.keys())
    sorted_seconds_server_to_client = sorted(bytes_server_to_client.keys())
    
    # Create intervals for plotting
    intervals_client_to_server = [datetime.fromtimestamp(sec) for sec in sorted_seconds_client_to_server]
    intervals_server_to_client = [datetime.fromtimestamp(sec) for sec in sorted_seconds_server_to_client]

    # Create figure with two subplots
    plt.figure(figsize=(12, 12))

    # Plot bytes per second for client-to-server and server-to-client
    plt.subplot(2, 1, 1)
    plt.plot(sorted_seconds_client_to_server, [bytes_client_to_server[sec] for sec in sorted_seconds_client_to_server], marker='o', linestyle='-', color='b', label='Client to Server')
    plt.plot(sorted_seconds_server_to_client, [bytes_server_to_client[sec] for sec in sorted_seconds_server_to_client], marker='o', linestyle='--', color='g', label='Server to Client')
    plt.xlabel('Seconds')
    plt.ylabel('Total Bytes')
    plt.title('Total Bytes Transferred per Second')
    plt.xticks()
    plt.grid(True)
    plt.legend()

    # Plot packets per second for client-to-server and server-to-client
    plt.subplot(2, 1, 2)
    plt.plot(sorted_seconds_client_to_server, [packets_client_to_server[sec] for sec in sorted_seconds_client_to_server], marker='o', linestyle='-', color='b', label='Client to Server')
    plt.plot(sorted_seconds_server_to_client, [packets_server_to_client[sec] for sec in sorted_seconds_server_to_client], marker='o', linestyle='--', color='g', label='Server to Client')
    plt.xlabel('Seconds')
    plt.ylabel('Number of Packets')
    plt.title('Number of Packets Transferred per Second')
    plt.xticks()
    plt.grid(True)
    plt.legend()

    # Format x-axis to show only seconds
    for ax in plt.gcf().axes:
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: int(x)))

    # Show the plots
    plt.tight_layout()
    plt.savefig('graph.png')
    plt.show()

def plot_graphs(pcap_file, client_ip, server_ip):
    # Run commands for both server-to-client and client-to-server traffic
    write_tshark_output_to_file(pcap_file, client_ip, server_ip, 'client_to_server.txt')
    write_tshark_output_to_file(pcap_file, server_ip, client_ip, 'server_to_client.txt')
    
    # Process data for both directions
    client_to_server_bytes, client_to_server_packets = process_data('client_to_server.txt')
    server_to_client_bytes, server_to_client_packets = process_data('server_to_client.txt')

    # Plot data for both directions in the same figures
    plot_two_directions(client_to_server_bytes, server_to_client_bytes, client_to_server_packets, server_to_client_packets)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pcap_file')
    parser.add_argument('--plot',action='store_true')
    parser.add_argument('--throughput',action='store_true')
    args = parser.parse_args()

    handshake1, handshake2 = find_ndt7_tls_handshakes(args.pcap_file)

    client_ip, server_ip = find_client_and_server_ips(handshake1)
    # print(client_ip,server_ip)

    tcp_fin_packet = find_tcp_fin_packet(args.pcap_file,client_ip,server_ip)

    # print(f"Found FIN packet:\n  Timestamp: {tcp_fin_packet.sniff_time}")
    # print(f"  Source IP: {tcp_fin_packet.ip.src if 'IP' in tcp_fin_packet else tcp_fin_packet.ipv6.src}")
    # print(f"  Destination IP: {tcp_fin_packet.ip.dst if 'IP' in tcp_fin_packet else tcp_fin_packet.ipv6.dst}")
    # print(f"  Source Port: {tcp_fin_packet.tcp.srcport}")
    # print(f"  Destination Port: {tcp_fin_packet.tcp.dstport}")

    download_test_flag = is_download_test(args.pcap_file, client_ip, server_ip, handshake1.sniff_time, 0.5)
    # print(download_test_flag)

    test_traffic_frac = find_ndt7_test_traffic_fraction(args.pcap_file,client_ip,server_ip)
    print(f'Speed test traffic percentage : {test_traffic_frac*100}%')

    if args.throughput:
        find_speeds(args.pcap_file,client_ip,server_ip,handshake1,handshake2,tcp_fin_packet,download_test_flag)
    
    if args.plot:
        plot_graphs(args.pcap_file,client_ip,server_ip)

if __name__ == '__main__':
    main()


