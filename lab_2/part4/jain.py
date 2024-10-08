import os
import json

def read_times(num_clients):
    times = []
    avg = 0
    x = 0
    for i in range(1, num_clients + 1):
        filename = f'time_{i}.txt'
        try:
            with open(filename, 'r') as f:
                line = f.readline().strip()
                # Extracting the time from the file
                time_value = float(line)
                avg += time_value
                x += 1
                times.append(1.0/time_value)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
    return times, (avg/x)

def jains_fairness_index(times):
    n = len(times)
    if n == 0:
        return 0
    sum_times = sum(times)
    sum_squares = sum(t ** 2 for t in times)
    return (sum_times ** 2) / (n * sum_squares) if sum_squares != 0 else 0

if __name__ == "__main__":
    with open('config.json') as f:
        config = json.load(f)

    times,avg = read_times(config['num_clients'])
    
    if times:
        jfi = jains_fairness_index(times)
        print(f"Jain's Fairness Index: {jfi}")
        print(f"Avg completion time: {avg}")
        try:
            with open('answer.txt', 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        if len(lines) >= 2:
            # If the file has 2 or more lines, erase and write on the first line
            with open('answer.txt', 'w') as f:
                f.write(f"Jain's Fairness Index: {jfi}\n")
                f.write(f"Avg completion time: {avg}\n")
        else:
            # If the file has less than 2 lines, append the content
            with open('answer.txt', 'a') as f:
                f.write(f"Jain's Fairness Index: {jfi}\n")
                f.write(f"Avg completion time: {avg}\n")
    else:
        print("No valid time data found.")
