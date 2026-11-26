# Lab 2: Socket Programming

Assignment 2 of COL334/672 (Diwali '24). A C++ TCP client/server word counter built with pthreads. It is extended in stages to concurrent clients, then to decentralized and then centralized ways of sharing a server that handles one request at a time.

## Contents

| Path | Description |
| --- | --- |
| `Assignment2-2.pdf` | Problem statement |
| `report.pdf` | Report with plots and discussion |
| `part1/` | Single word-counting client |
| `part2/` | Concurrent clients |
| `part3/` | "Grumpy" server: slotted ALOHA, binary exponential backoff (BEB), and carrier sensing with BEB |
| `part4/` | "Friendly" server: FIFO and round-robin scheduling, plus a fairness study with a rogue client |

Every part has:

- `config.json`: server IP and port, `k`, `p`, input file and number of clients.
- `words.txt`: the comma-separated word list.
- `json.hpp`: the nlohmann/json single-header library.
- A `Makefile`.
- `results.json`: the raw numbers behind the report's plots.

## Common protocol

- The client opens a TCP connection and sends `<offset>\n`.
- The server replies with up to `k` words starting at that offset, `p` words per packet.
  - Words inside a packet are comma-separated, and each packet ends with `\n`.
  - The last word of the file is followed by `,EOF`.
  - An offset past the end of the file gets the reply `$$\n`.
- The client moves the offset forward by `k` until it sees `EOF`. It then writes `word, count` lines in dictionary order.

## Part 1: Word-counting client

- `server.cpp` loads the word list into memory and serves one client. It exits after one complete download.
- `client.cpp` writes the counts to `output.txt` and the completion time to `time.txt`. Logs go to `client_log.txt` and `server_log.txt`.
- `plot.py` tries each `p` from 1 to 10 with 10 runs each. It plots the mean completion time with ±1 standard-deviation error bars to `plot.png` and saves the raw times to `results.json`. While it runs, it rewrites `p` in `config.json`.

**Finding:** completion time falls as `p` grows, because fewer packets carry the same data. Mean times in `results.json`:

| `p` | Mean completion time |
| --- | --- |
| 1 | ≈157 ms |
| 5 | ≈87 ms |
| 10 | ≈62 ms |

## Part 2: Concurrent clients

- The server starts one pthread per accepted connection. It shuts down after `num_clients` downloads have finished.
- The client starts `num_clients` threads, each with its own connection. Each thread retries `connect` up to 50 times, 1 s apart, and writes `output_<i>.txt` and `time_<i>.txt`.
- `plot.py` sweeps n = 1, 5, …, 29 clients with 5 runs each.

**Finding:** average completion time per client grows roughly linearly with n, from about 98 ms at n = 1 to about 1.3 s at n = 29. The report blames context switching once there are more threads than cores, and contention on shared memory.

## Part 3: Grumpy server

The server serves one request at a time. If a request arrives while another is being served, it sends `HUH!\n` to both clients. Each client then throws away the words it received for that request and retries.

| Protocol | Files | Behaviour |
| --- | --- | --- |
| Slotted ALOHA | `server_aloha.cpp`, `client_aloha.cpp` | Time is split into T ms slots aligned to multiples of T in UNIX milliseconds. At the start of each slot a client transmits with probability 1/n. The server treats two or more requests in the same slot as a collision. |
| BEB | `server_beb.cpp`, `client_beb.cpp` | The server tracks a busy flag and the time of the last collision, as the handout suggests. After its k-th collision a client waits i·T ms, with i drawn uniformly from [0, 2^min(k,10) − 1]. |
| Sensing + BEB | `server_cscd.cpp`, `client_cscd.cpp` | The client sends `BUSY?\n`, and the server answers `BUSY\n` or `IDLE\n` without changing its state. On `BUSY` the client waits T ms and asks again. On `IDLE` it sends the data request. If it then gets `HUH!`, it falls back to BEB. |

`plotx.py` (run it with `make plot`) runs each protocol with n = 1 to 10 clients. It plots average completion time per client against n to `plot.png`, writes the numbers and the n values to `results.json`, and then restores `config.json`.

**Finding:** the committed `results.json` comes from the original runs. It holds 10 measurements per protocol, each an average completion time per client in ms, but does not record the n values. ALOHA rises from about 17 ms to about 338 ms across them, while BEB and sensing + BEB stay between roughly 3 and 15 ms. The report explains this as follows:

- ALOHA's efficiency stays close to 1/e, so it cannot keep up as clients are added.
- Exponential backoff sharply reduces repeated collisions.
- Sensing reduces collisions further.
- A larger slot length T hurts ALOHA, and a higher transmit probability causes more collisions.

## Part 4: Friendly server

- `server.cpp` (FIFO): connection threads push `(socket, offset)` requests onto one global queue. A single worker thread serves them in arrival order, using a mutex and a condition variable.
- `server_rr.cpp` (round-robin): each connection gets its own queue. The worker cycles through the connections and serves one request from each non-empty queue in turn.
- `client_rogue.cpp`: client 1 is the rogue. It runs 5 sender threads that issue requests concurrently on one connection, with a shared receiver thread. All other clients behave normally.
- `jain.py` reads `time_<i>.txt`, computes Jain's fairness index over 1/time, and prints the index and the average completion time. It also writes them to `answer.txt`.

**Findings:**

- FIFO and round-robin give similar average completion times. Both rise from about 69 ms at n = 1 to about 1.6–1.9 s at n = 29. The report argues that the policy cannot change the average when the server handles one request at a time.
- Centralized queuing is slower than the decentralized protocols in Part 3 because of head-of-line blocking.
- In the rogue-client experiment, round-robin always scored a higher Jain's index than FIFO.

## Building and running

Requirements: Linux, `g++` with C++17 and pthreads, Python 3 with `numpy` and `matplotlib`. All four parts build with `make build`.

| Part | Make targets |
| --- | --- |
| part1 | `make build`, `make run` (one server and one client), `make plot` |
| part2 | `make build`, `make run`, `make plot` |
| part3 | `make build`, `make run_aloha`, `make run_beb`, `make run_cscd`, `make run_all`, `make plot` |
| part4 | `make build`, `make run-fifo`, `make run-rr`, `make run` (both), `make fairness`, `make plot`, `make plot-rogue` |

Every target reads `config.json` from the part's directory.

> **Warning:** the run targets clean up old servers with `pkill -9 server` (and `server_rr`, `server_aloha`, and so on). `pkill` matches any process whose name contains that text, so this can kill unrelated programs on your machine. To avoid that, start `./server &` and then `./client` by hand.

## Notes and known issues

### Part 1

- Word counts go to `output.txt`, not stdout.
- The plot's error bars are standard deviations, not confidence intervals.

### Part 3

- The make targets use underscores (`run_aloha`), not the handout's `run-aloha`, and there is no `run` target.
- On Linux, every request takes about 41 ms, so one run takes about 40 s for any n and protocol, and the plot is nearly flat. The servers send each word with its own `send()`, and this matches the clash between Nagle's algorithm and delayed ACKs. In a test, setting `TCP_NODELAY` on the sensing server's accepted sockets cut a single client's download from about 40 s to about 0.1 s. A full `make plot` (30 runs) takes about 20–25 minutes.
- On Linux, a server can keep running after its last client finishes, because closing the listening socket doesn't wake the thread blocked in `accept()`. I saw this with the sensing server, and the other two shut down the same way. After a `run_*` target, stop the server yourself. `make plot` stops each server it starts.
- `T` in `config.json` is the slot length and backoff unit in whole milliseconds, and the code reads it as an `int`. A fractional value such as `0.1` becomes `0`, which makes ALOHA divide by zero and makes every backoff wait zero. The config uses `T = 1`, the smallest value the report tested; the report also tried 5 and 50.

### Part 4

- The `make fairness` study is meant to use 10 clients, but `config.json` currently has `num_clients: 29`.
- The `server-rr` and `client-rr` targets start the FIFO `server` binary. Use `make run-rr` instead.
- `jain.py` prints labelled lines, with times in microseconds. The handout asked for comma-separated values.
