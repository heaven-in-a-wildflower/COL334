"""Part 3 analysis: average completion time per client vs. number of clients
for slotted ALOHA, BEB and sensing + BEB (CSCD).

Run via `make plot` (which builds the binaries first). For each protocol and
each client count it starts the server, runs the client program, and reads the
per-client completion times from time_<i>.txt. Outputs plot.png and
results.json. config.json is restored to its original contents afterwards.
"""
import glob
import json
import os
import re
import subprocess
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# results.json key -> binary suffix (server_<suffix>, client_<suffix>)
PROTOCOLS = {"Aloha": "aloha", "BEB": "beb", "CSCD": "cscd"}
CLIENT_COUNTS = list(range(1, 11))
NUM_RUNS = 1                 # runs averaged per (protocol, client count)
SERVER_STARTUP_DELAY = 1.0   # seconds; the clients do not retry connect()
CLIENT_TIMEOUT = 600         # seconds allowed for one run of the client program

TIME_PATTERN = re.compile(r"Completion time = (\d+)")


def read_completion_times_ms(num_clients):
    times = []
    for i in range(1, num_clients + 1):
        path = f"time_{i}.txt"
        if not os.path.exists(path):
            raise RuntimeError(f"{path} missing: client {i} did not finish")
        with open(path) as f:
            match = TIME_PATTERN.search(f.read())
        if not match:
            raise RuntimeError(f"Could not parse completion time in {path}")
        times.append(int(match.group(1)) / 1000.0)  # microseconds -> ms
    return times


def run_once(suffix, num_clients):
    """Run one server/client experiment; return the mean completion time (ms)."""
    for path in glob.glob("time_*.txt") + glob.glob(f"client_{suffix}_*_log.txt"):
        os.remove(path)

    server = subprocess.Popen([f"./server_{suffix}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(SERVER_STARTUP_DELAY)
        if server.poll() is not None:
            raise RuntimeError(f"server_{suffix} exited early (is the port already in use?)")
        subprocess.run([f"./client_{suffix}"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=CLIENT_TIMEOUT, check=True)
    finally:
        if server.poll() is None:
            server.terminate()
        server.wait()

    times = read_completion_times_ms(num_clients)
    return sum(times) / len(times)


def main():
    for suffix in PROTOCOLS.values():
        for binary in (f"server_{suffix}", f"client_{suffix}"):
            if not os.path.exists(binary):
                raise SystemExit(f"./{binary} not found; run `make build` first")

    with open("config.json") as f:
        original_config = f.read()
    config = json.loads(original_config)

    results = {label: [] for label in PROTOCOLS}
    try:
        for n in CLIENT_COUNTS:
            config["num_clients"] = n
            with open("config.json", "w") as f:
                json.dump(config, f)
            for label, suffix in PROTOCOLS.items():
                runs = [run_once(suffix, n) for _ in range(NUM_RUNS)]
                avg = sum(runs) / len(runs)
                results[label].append(avg)
                print(f"{label:5s} n={n:2d}: {avg:.2f} ms average completion time per client",
                      flush=True)
    finally:
        with open("config.json", "w") as f:
            f.write(original_config)

    for label, values in results.items():
        plt.plot(CLIENT_COUNTS, values, "-o", label=label)
    plt.xticks(CLIENT_COUNTS)
    plt.xlabel("n (number of clients)")
    plt.ylabel("Average completion time per client (ms)")
    plt.title(f"Completion time vs. number of clients (T = {config['T']} ms)")
    plt.legend()
    plt.grid(True)
    plt.savefig("plot.png")

    with open("results.json", "w") as f:
        json.dump({"num_clients": CLIENT_COUNTS, **results}, f)


if __name__ == "__main__":
    main()
