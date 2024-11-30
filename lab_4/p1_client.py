import socket
import argparse
import json
import time

MSS = 1400
BUFFER_SIZE = MSS + 1024
TIMEOUT = 1

def parse_packet(packet):
    try:
        packet_dict = json.loads(packet.decode('utf-8'))
        return (packet_dict['sequence_number'],
                packet_dict['fin'], 
                packet_dict['data'].encode('utf-8') if isinstance(packet_dict['data'], str) else packet_dict['data'])
    except:
        return (-1, None)

def create_ack(seq_num):
    ack_dict = {'ack_number': seq_num}
    return json.dumps(ack_dict).encode('utf-8')

def receive_file(server_ip, server_port):
    timeout = TIMEOUT
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(timeout)
    server_address = (server_ip, server_port)
    done = -1
    expected_seq_num = 0
    received_buffer = {}
    output_file = "received_file.txt"

    print("Sending initial connection request...")
    client_socket.sendto(b"START", server_address)

    with open(output_file, 'wb') as file:
        while True:
            try:
                packet, _ = client_socket.recvfrom(BUFFER_SIZE)
                seq_num, fin, data = parse_packet(packet)
                print(f"Received packet {seq_num}")

                if fin == 2 and done:
                    print("Received end of transmission signal")
                    break

                if fin == 1:
                    print("Received last packet")
                    done = seq_num + len(data)

                if seq_num == expected_seq_num:
                    file.write(data)
                    file.flush()
                    print(f"Received and wrote packet {seq_num}")
                    expected_seq_num += len(data)

                    while expected_seq_num in received_buffer:
                        file.write(received_buffer[expected_seq_num])
                        data_len = len(received_buffer[expected_seq_num])
                        del received_buffer[expected_seq_num]
                        expected_seq_num += data_len
                
                elif seq_num > expected_seq_num:
                    print(f"Received out-of-order packet {seq_num}, buffering")
                    received_buffer[seq_num] = data

                print(f"Sent packet {expected_seq_num}")
                ack = create_ack(expected_seq_num)
                client_socket.sendto(ack, server_address)
                timeout_count = 0
                timeout = TIMEOUT
                client_socket.settimeout(timeout)

            except socket.timeout:
                if expected_seq_num > 0:
                    print(f"Timeout waiting for data, sending duplicate ACK {expected_seq_num}")
                    dup_ack = create_ack(expected_seq_num)
                    client_socket.sendto(dup_ack, server_address)
                    if done == expected_seq_num:
                        timeout_count += 1
                        if (timeout_count == 3):
                            print("Closing connection assuming server has closed")
                            break
                else:
                    print("Sending initial connection request...")
                    client_socket.sendto(b"START", server_address)
                timeout *= 2
                client_socket.settimeout(timeout)

            except Exception as e:
                print(f"Error: {e}")
                break

    client_socket.close()
    print("File transfer complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
    parser.add_argument('server_ip', help='IP address of the server')
    parser.add_argument('server_port', type=int, help='Port number of the server')
    args = parser.parse_args()
    
    receive_file(args.server_ip, args.server_port)