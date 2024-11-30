import socket
import time
import argparse
import json
import math

MSS = 1400
DUP_ACK_THRESHOLD = 3
FILE_PATH = "report.txt"
INITIAL_TIMEOUT = 0.5
ALPHA = 0.125
BETA = 0.25
TARGET_SPEED = 50*(10**6)/8

def create_packet(seq_num, data, fin=0):
    packet_dict = {
        'sequence_number': seq_num,
        'data_length': len(data),
        'fin': fin,
        'data': data.decode('utf-8') if isinstance(data, bytes) else data
    }
    return json.dumps(packet_dict).encode('utf-8')

def parse_ack(ack_packet):
    try:
        ack_data = json.loads(ack_packet.decode('utf-8'))
        return ack_data.get('ack_number', -1)
    except:
        return -1

def calculate_timeout(srtt, rttvar):
    return srtt + 4 * rttvar

def update_rtt_stats(sample_rtt, srtt, rttvar):
    if srtt == 0:
        srtt = sample_rtt
        rttvar = sample_rtt / 2
    else:
        rttvar = (1 - BETA) * rttvar + BETA * abs(srtt - sample_rtt)
        srtt = (1 - ALPHA) * srtt + ALPHA * sample_rtt
    return srtt, rttvar

def calculate_window_size(rtt):
    return math.ceil((TARGET_SPEED * rtt) / MSS)

def send_file(server_ip, server_port, enable_fast_recovery):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))
    print(f"Server listening on {server_ip}:{server_port}")

    srtt = 0
    rttvar = 0
    rto = INITIAL_TIMEOUT
    window_size = 1
    window_base = 0
    next_to_send = 0
    unacked_packets = {}
    dup_ack_count = 0

    client_address = None
    with open(FILE_PATH, 'rb') as file:
        
        sent2 = False
        sent1 = -1
        rec1 = False
        next_chunk = file.read(MSS)
        
        while True:
            # Send packets within window
            while next_to_send < window_base + window_size*MSS:

                if client_address:
                    chunk = next_chunk
                    next_chunk = file.read(MSS)
                    if not chunk:
                        if rec1 and not unacked_packets:
                            sent2 = True
                            print("Sending last packet ack")
                            chunk = "END"
                            packet = create_packet(next_to_send, "END", 2)
                            server_socket.sendto(packet, client_address)
                            server_socket.sendto(packet, client_address)
                            server_socket.sendto(packet, client_address)
                            print(f"Closing server assuming client has the info")
                            server_socket.close()
                            return
                        else:
                            break
                    elif not next_chunk:
                        if sent1 < 0:
                            print("Sending last packet")
                            packet = create_packet(next_to_send, chunk, 1)
                            sent1 = next_to_send + len(chunk)
                        else:
                            break
                    else:
                        packet = create_packet(next_to_send, chunk)
                    server_socket.sendto(packet, client_address)
                    if not unacked_packets:
                        server_socket.settimeout(rto)
                    unacked_packets[next_to_send] = (packet, time.time(), 1)
                    print(f"Sent packet {next_to_send}")
                    next_to_send += len(chunk)
                    if not next_chunk:
                        break
                else:
                    print("Waiting for client connection...")
                    _, client_address = server_socket.recvfrom(1024)
                    print(f"Connection established with client {client_address}")

            try:
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_num = parse_ack(ack_packet)
                print(f"Received ack {ack_num}")

                if ack_num == sent1 and sent1 > 0:
                    print("Received last ack")
                    rec1 = True
                    unacked_pkts = list(unacked_packets.keys())
                    for seq in unacked_pkts:
                        if seq < ack_num:
                            del unacked_packets[seq]
                    window_base = ack_num
                    dup_ack_count = 0

                elif ack_num > window_base:
                    # Calculate RTT for this ACK
                    if ack_num == window_base + MSS and unacked_packets[window_base][2]:
                        send_time = unacked_packets[window_base][1]
                        sample_rtt = time.time() - send_time
                        srtt, rttvar = update_rtt_stats(sample_rtt, srtt, rttvar)
                        window_size = calculate_window_size(srtt)
                        rto = calculate_timeout(srtt, rttvar)
                        print(f"Updated window size: {window_size}")
                    
                    server_socket.settimeout(rto)

                    # Remove acknowledged packets
                    for seq in range(window_base, ack_num, MSS):
                        if seq in unacked_packets:
                            del unacked_packets[seq]
                    
                    window_base = ack_num
                    dup_ack_count = 0
                
                elif ack_num == window_base or ack_num == -1:
                    ack_num = window_base
                    dup_ack_count += 1
                    if sent2:
                        if dup_ack_count >= 3:
                            print(f"Closing server assuming client has the info")
                            server_socket.close()
                            break
                        if ack_num in unacked_packets:
                            server_socket.sendto(unacked_packets[ack_num][0], client_address)
                            unacked_packets[ack_num] = (unacked_packets[ack_num][0], time.time(), 0)
                    if enable_fast_recovery and dup_ack_count == DUP_ACK_THRESHOLD:
                        if ack_num in unacked_packets:
                            print(f"Fast Recovery: Retransmitting packet {ack_num}")
                            server_socket.sendto(unacked_packets[ack_num][0], client_address)
                            unacked_packets[ack_num] = (unacked_packets[ack_num][0], time.time(), 0)
                
                elif rttvar > 0:
                    rto = calculate_timeout(srtt, rttvar)

            except socket.timeout:
                print(f"Timeout occurred. RTO: {rto:.2f}s")
                for seq in unacked_packets:
                    server_socket.sendto(unacked_packets[seq][0], client_address)
                    unacked_packets[seq] = (unacked_packets[seq][0], time.time(), 0)
                if rto < 3*calculate_timeout(srtt, rttvar):
                    rto *= 2
                server_socket.settimeout(rto)
                dup_ack_count = 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    parser.add_argument('fast_recovery', type=int, help='Enable fast recovery (1/0)')
    args = parser.parse_args()
    send_file(args.server_ip, args.server_port, args.fast_recovery)