# Lab 4: TCP-like Reliable Transfer over UDP

Assignment 4 of COL334/672 (Diwali '24). A Python file-transfer protocol over UDP. It adds reliability (cumulative ACKs, retransmission timeouts and fast retransmit), TCP Reno congestion control, and TCP CUBIC as the bonus. Experiments run in Mininet.

## Contents

| File | Description |
| --- | --- |
| `Assignment4.pdf` | Problem statement |
| `report_col334_lab4.pdf` | Report: design, plots and analysis |
| `p1_server.py`, `p1_client.py` | Part 1: reliability only, sending at a fixed 50 Mbps, with fast recovery that can be switched on or off |
| `p1_exp.py` | Mininet driver for the Part 1 loss and delay sweeps. Writes `reliability_<exp>.csv` |
| `p2_server.py`, `p2_client.py` | Part 2: TCP Reno congestion control |
| `p2_exp_fairness.py` | Mininet dumbbell fairness experiment. Writes `p2_fairness.csv` and `jfi_vs_latency.png` |
| `p3_server.py`, `p3_client.py` | Part 3 (bonus): TCP CUBIC. `p3_client.py` is identical to `p2_client.py` |
| `report.txt` | The file every server sends. The name is hard-coded |
| `reliability_loss.csv`, `reliability_delay.csv`, `p2_fairness.csv` | Experiment output |
| `*.log`, `*received_file.txt`, `client_output.txt`, `server_output.txt` | Leftovers from earlier runs |
| `5_6206049308303693091.txt` | A copy of `p1_exp.py` with Windows (CRLF) line endings |

## Problem statement

1. **Reliability (40%).**
   - Use cumulative ACKs and sequence numbers, retransmit on timeout or on 3 duplicate ACKs, and estimate the RTO as taught in class.
   - Measure how much fast recovery helps when the h1–s1 link has a 20 ms delay and 0–5% loss, and when it has 1% loss and 0–200 ms delay.
2. **Congestion control (60%).**
   - Implement TCP Reno: slow start, congestion avoidance, fast recovery and timeout behaviour, with an MSS of 1400 B and an initial window of 1 MSS.
   - Measure throughput against delay and against loss.
   - Measure fairness on a dumbbell topology while the delay of the Switch2–Server2 link varies from 0 to 100 ms.
3. **Bonus (20%).**
   - Implement TCP CUBIC with W(t) = C(t − K)³ + W_max, C = 0.4 and β = 0.5.
   - Compare its efficiency with Reno, and compare Reno against CUBIC on short-delay (2 ms) and long-delay (25 ms) paths.

## Design

### Wire format

Messages are JSON over UDP, and the MSS is 1400 bytes.

| Message | Format |
| --- | --- |
| Data | `{"sequence_number": <first byte offset>, "data_length": <n>, "fin": 0 \| 1 \| 2, "data": "<payload>"}` |
| ACK | `{"ack_number": <next expected byte>}` |

- `fin = 1` marks the last data packet.
- `fin = 2` is the `END` packet. The server sends it three times once all data has been acknowledged.
- To start a transfer, the client sends `START`. It resends with exponential backoff until data arrives.
- The client buffers out-of-order packets and writes bytes to the file in order.

### Part 1: Reliability (`p1_server.py`)

- **RTT estimation:** SRTT and RTTVAR with α = 1/8 and β = 1/4. RTO = SRTT + 4·RTTVAR, starting at 0.5 s.
- **Karn's rule:** RTT samples come only from packets that were never retransmitted.
- **Timeout:** the server resends every unacknowledged packet and doubles the RTO while it stays below 3× the computed value.
- **Fast retransmit:** on the third duplicate ACK, if `FAST_RECOVERY_BOOL` is 1.
- **No congestion control:** the window is ⌈50 Mbps × SRTT / MSS⌉ packets, which gives a fixed sending rate of 50 Mbps.

### Part 2: TCP Reno (`p2_server.py`)

The Part 1 reliability code is kept, and `cwnd` (counted in MSS) starts at 1 with `ssthresh` at infinity.

| Event | Action |
| --- | --- |
| New ACK, slow start | `cwnd += 1` |
| New ACK, congestion avoidance | `cwnd += 1/cwnd` |
| 3 duplicate ACKs | Retransmit, `ssthresh = cwnd/2`, `cwnd = ssthresh + 3`, enter fast recovery |
| Further duplicate ACKs during fast recovery | `cwnd += 1` |
| New ACK during fast recovery | `cwnd = ssthresh`, leave fast recovery |
| Timeout | `ssthresh = cwnd/2`, `cwnd = 1`, back to slow start |

- After a timeout, unacknowledged packets are queued and resent as `cwnd` allows, instead of all at once.
- RTO = max(1 s, SRTT + 4·RTTVAR), starting at 1 s.

### Part 3: TCP CUBIC (`p3_server.py`)

- Identical to Part 2 except during congestion avoidance, where `cwnd = C(t − K)³ + W_max` with C = 0.4 and K = ∛(W_max·β / C), β = 0.5.
- `cwnd` never drops below 1.
- `W_max` and the start time `t` reset on every loss event, whether it is 3 duplicate ACKs or a timeout.

## Running

The server sends `report.txt` from its working directory. Replace it with the file you want to transfer.

```bash
# Part 1
python3 p1_server.py <SERVER_IP> <SERVER_PORT> <FAST_RECOVERY 0|1>
python3 p1_client.py <SERVER_IP> <SERVER_PORT>                            # writes received_file.txt

# Part 2 (Reno) and Part 3 (CUBIC)
python3 p2_server.py <SERVER_IP> <SERVER_PORT>                            # or p3_server.py
python3 p2_client.py <SERVER_IP> <SERVER_PORT> --pref_outfile <PREFIX>    # writes <PREFIX>received_file.txt
```

### Mininet experiments

The experiment scripts connect to a remote controller at `127.0.0.1:6653`, so a learning-switch controller must be running there. The Lab 3 learning switch works. The scripts need root.

```bash
ryu-manager --ofp-tcp-listen-port 6653 ../lab_3/p1_learning.py

sudo python3 p1_exp.py loss       # loss 0–5% in 0.5% steps, 20 ms delay -> reliability_loss.csv
sudo python3 p1_exp.py delay      # delay 0–200 ms in 20 ms steps, 1% loss -> reliability_delay.csv
sudo python3 p2_exp_fairness.py   # dumbbell, Switch2–Server2 delay 0–100 ms -> p2_fairness.csv, jfi_vs_latency.png
```

- **`p1_exp.py`** runs the server on h1 (`10.0.0.1:6555`) and the client on h2. It does 5 runs for each setting, with fast recovery both off and on. Each row records the completion time and the MD5 of the received file.
- **`p2_exp_fairness.py`** builds this topology:
  - Clients `c1` and `c2` connect to `sw1`.
  - `sw1` connects to `sw2` over a 100 Mbps, 5 ms bottleneck link with a 500-packet queue.
  - Servers `s1` and `s2` connect to `sw2`.
  - Every other link has a 5 ms delay, except the `sw2`–`s2` link, which the script varies.

  It runs each setting twice and computes Jain's index over the two clients' 1/completion-time values.

## Findings

These come from `report_col334_lab4.pdf`.

- **Part 1:** fast recovery slightly reduced completion time, and the gap grew with loss. The gain was not consistent, though; for example, it did not help at 80 ms and 100 ms delay. These results average 10 runs with a 50 MB file. MD5 hashes of every received file matched the original.
- **Part 2:** completion time grows with both loss and delay. Jain's index falls roughly linearly as the delay on the second path grows, because Reno is not RTT-fair. The report gives normalized index values mostly between 0.8 and 0.9.
- **Part 3:** CUBIC achieved higher average throughput than Reno in almost every case and was fairer across different RTTs.

## Notes and known issues

- The servers send a hard-coded `report.txt`, not the handout's `file.txt`. The committed `report.txt` is a 1,522-byte text file, which fits in two packets.
- The MD5 in every row of `reliability_loss.csv` and `reliability_delay.csv` matches `report.txt`. Those CSVs therefore come from runs with that small file, not the 50 MB runs in the report, so the completion times mostly reflect link delay.
- `p2_fairness.csv` has only a header row.
- The repo has no experiment script for Part 3 (Reno vs CUBIC) and no plotting scripts for the Part 1 and Part 2 efficiency plots.
- Payloads are decoded as UTF-8 text, so the code expects plain-text, effectively ASCII, files. Binary files, or a multi-byte character split across two 1400-byte chunks, will fail to decode.
- `p2_exp_fairness.py` uses `s1`/`s2` as server host names and `sw1`/`sw2` as switches. Its server IPs (`10.0.0.3`, `10.0.0.4`) rely on Mininet assigning addresses in the order the hosts are added.
