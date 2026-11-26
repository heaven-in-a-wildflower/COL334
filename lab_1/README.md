# Lab 1: Getting to Know Network Traffic

Assignment 1 of COL334/672 (Diwali '24). This lab covers basic network measurement with `ping` and `traceroute`, capturing and dissecting a Microsoft Teams call, and analysing an M-Lab NDT7 speed-test trace with a Python script.

## Contents

| File | Description |
| --- | --- |
| `assignment1.pdf` | Problem statement |
| `col334_lab1-2.pdf` | Report: answers, screenshots and plots for all three parts |
| `speedtest_analysis.py` | Part 3 script. It isolates the NDT7 traffic, plots throughput over time and computes average download/upload speeds |

Two things are not in this folder: the Teams-call capture from Part 2 (the report links to it externally) and the NDT7 trace that Part 3 analyses.

## Problem statement

1. **Measurement tools**
   - Ping `google.com` and `sigcomm.org` from the IITD network and from a mobile hotspot, then compare the latencies.
   - Explain the protocol `ping` uses and its maximum packet size, and try forcing IPv6.
   - Traceroute each (website, network) pair. Report hop counts, the autonomous systems on the path, `*` hops, multiple IPs at one hop, reachability of the first-hop router, tiered Internet structure, and IP geolocation compared with RTT.
2. **Network data collection**
   - Capture a 1-minute, two-person Teams call with video and microphone on.
   - Report the protocol mix and whether the two hosts talk directly.
   - Separate audio from video packets and plot bandwidth over time.
3. **Traffic analysis**
   - Given an NDT7 speed-test PCAP, separate the test traffic from background traffic.
   - Plot per-second throughput in each direction and report average download and upload speeds.
   - Do this with a script called `speedtest_analysis.py` that supports `--plot` and `--throughput`.

## Approach and findings

These numbers come from `col334_lab1-2.pdf`.

### Part 1: ping and traceroute

| Average ping RTT | google.com | sigcomm.org |
| --- | --- | --- |
| IITD Wi-Fi | 87.327 ms | 352.485 ms |
| Mobile hotspot | 42.371 ms | 564.346 ms |

- The report attributes Google's lower latency to CDN caching close to users and to direct peering with ISPs.
- `ping` uses ICMP Echo Request/Reply. The theoretical maximum payload is 65,507 B over IPv4 (65,535 − 20 − 8) and 65,487 B over IPv6 (65,535 − 40 − 8). In practice the 1500 B Ethernet MTU limits the largest unfragmented payload to 1472 B (IPv4) and 1452 B (IPv6) on IITD Wi-Fi.
- With IPv6 forced, `google.com` answered on both networks. `sigcomm.org` failed on IITD Wi-Fi ("address family for hostname not supported") but worked over the hotspot.
- Traceroute hop counts:
  - `google.com`: 9 hops on Wi-Fi, 15 on the hotspot.
  - `sigcomm.org`: 15 hops on Wi-Fi, 18 on the hotspot.
  - Autonomous systems seen include AS15169 (Google), AS55836 (Reliance Jio), AS3356 (Level 3) and AS55293.
- The first hop on IITD Wi-Fi (`10.184.0.13`) is a private address, so it does not respond to pings from mobile data.
- The path to Google looked two-tiered because of direct peering. The paths to `sigcomm.org` showed a three-tier structure.

### Part 2: Teams call capture

The call was captured in two setups: app-to-app (macOS and Windows 11) and browser-to-browser (macOS and Ubuntu 24.04).

- About 99% of the traffic was UDP in both setups.
  - The browser call was mostly IPv6 and carried SRTP, STUN and QUIC.
  - The app call was mostly IPv4, with a large share of STUN and some RTP.
- **App-to-app:** both hosts were behind NAT and there was no direct connection. Both exchanged media with the same Microsoft server, which acted as a relay.
- **Browser-to-browser:** both hosts were on the same home Wi-Fi, and a direct connection was observed.
- Audio and video were told apart by port and by packet pattern:
  - The Teams app uses UDP ports 50000–50019 for audio and 50020–50039 for video.
  - Video packets are about 1000 B and arrive in bursts of 8–10. Audio packets are about 150 B and arrive singly.

### Part 3: `speedtest_analysis.py`

1. Use `pyshark` to find TLS ClientHello packets whose SNI starts with `ndt-mlab`.
2. The first ClientHello that is followed by a gap of more than 5 s marks the start of the first test. The last matching ClientHello marks the start of the second test.
3. Take the client and server IPs from the first handshake.
4. Work out whether the first test is the download or the upload by comparing bytes in each direction during the 0.5 s after it starts.
5. A TCP FIN from the server to the client marks the end of the second test.
6. Compute average throughput as the frame bytes in the test's direction divided by the test duration. The `tshark` filters do the byte counting.
7. Compute the speed-test share as the bytes exchanged between the client and server IPs divided by all bytes in the trace.

The report gives these results for the provided trace:

- The speed test is 65.42% of all traffic.
- Average download is about 29.52 Mbps.
- Average upload is about 8.52 Mbps.

## Running the script

Requirements: Python 3, `tshark` (Wireshark CLI) on `PATH`, and the Python packages `pyshark` and `matplotlib`.

```bash
python3 speedtest_analysis.py <trace.pcap> --plot        # bytes/s and packets/s per direction -> graph.png
python3 speedtest_analysis.py <trace.pcap> --throughput  # average download and upload speed in Mbps
```

Both modes also print the detected handshakes and the speed-test traffic percentage.

## Notes

- `--throughput` prints two labelled lines (`Average Download throughput= … Mbps`, then the upload line). The handout asked for one comma-separated pair.
- The handshake search handles both IPv4 and IPv6. The `tshark` filters used for throughput and plotting match on `ip.src`/`ip.dst`, so those steps only work on IPv4 traces.
- `--plot` leaves two intermediate files, `client_to_server.txt` and `server_to_client.txt`, in the working directory. It also calls `plt.show()`, so it needs a display.
