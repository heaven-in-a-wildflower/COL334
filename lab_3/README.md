# Lab 3: An Introduction to SDN

Assignment 3 of COL334/672 (Diwali '24). These are Ryu controller apps for Mininet networks: a hub compared with a learning switch, loop-free flooding using a spanning tree, and shortest-path routing.

## Contents

| File | Description |
| --- | --- |
| `Assignment-3.pdf` | Problem statement |
| `report.pdf` | Report: observations, screenshots, approach and assumptions |
| `p1_hub.py` | Part 1 hub controller (OpenFlow 1.0) |
| `p1_learning.py` | Part 1 learning switch (OpenFlow 1.0) |
| `p2_spanning_tree.py` | Part 2 learning switch with spanning-tree flooding (OpenFlow 1.3) |
| `p3_spr.py` | Part 3 shortest-path routing (OpenFlow 1.3) |

Not included:

- The Mininet topology files that came with the assignment.
- The bonus Part 4 app (`p4_ca_spr.py`, congestion-aware routing).

## Problem statement

1. **Hub vs learning switch (25%).** Run both controllers on the given two-switch topology. Report the installed rules after `pingall` and compare `iperf` throughput between h1 and h5.
2. **Spanning tree (40%).** Change the learning switch so it handles topologies with cycles. Build a spanning tree, with any algorithm and all link weights equal to 1, and send broadcasts only on tree ports and host ports. Test it on a four-switch cycle.
3. **Shortest-path routing (35%).** Route unicast traffic along shortest paths, with link weights based on link capacity, while still learning at L2.
4. **Bonus (20%).** Congestion-aware shortest-path routing based on live link utilization.

## Solution

### `p1_hub.py`

- Floods every packet-in with `OFPP_FLOOD` through a PacketOut.
- Installs no flows, so every packet passes through the controller.

### `p1_learning.py`

- Based on Ryu's `simple_switch.py` example, with explanatory comments added.
- Learns a MAC-to-port table for each switch and floods when the destination is unknown.
- Once the destination is known, installs a flow matching `(in_port, dl_src, dl_dst)`.

### `p2_spanning_tree.py`

- Uses Ryu's topology discovery (`EventSwitchEnter`, `EventLinkAdd`, `EventHostAdd`) to build a graph of the switches and to record which ports face hosts.
- Each time a link is added, recomputes a BFS spanning tree rooted at the lowest datapath ID.
- Installs a table-miss rule that sends packets to the controller.
- Floods unknown or broadcast destinations only on spanning-tree ports and host ports, excluding the port the packet came in on.
- For a known destination, installs a flow matching `(in_port, eth_dst)`.

### `p3_spr.py`

1. **Topology:** collects switches and links through the Ryu topology API. Host ports are switch ports that are not part of any inter-switch link.
2. **Link weights:**
   - Sends a custom LLDP probe on each link. The probe carries an extra TLV of type 127 with the value `latency_measurement`.
   - Times each probe's round trip through the controller.
   - Subtracts twice the controller-to-switch delay, which it estimates with OpenFlow echo requests.
   - Uses the result, rounded to 0.1 ms, as the link weight.
3. **Paths:** runs Dijkstra from every switch to build a next-hop table.
4. **Broadcasts:** floods broadcasts and unknown unicast along a BFS spanning tree, as in Part 2.
5. **Unicast:** finds the switch where the destination MAC was first seen and forwards towards it through the next hop. Installs a flow matching `(eth_src, eth_dst)`.

## Findings

These come from `report.pdf`.

- With the learning switch, after `pingall` s1 held 18 flow entries and s2 held 14. The hub installed none.
- In `iperf` between h1 and h5, the learning switch was about 280–300 times faster than the hub, and the hub runs consistently showed packet loss.
- On the looped topology, the plain learning switch caused a broadcast storm. `pingall` failed and CPU usage reached 100% on every core. The spanning-tree app fixes this.

## Running

Requirements: Mininet, Open vSwitch and Ryu.

1. Start the controller:

   ```bash
   # Part 1 (OpenFlow 1.0)
   ryu-manager p1_hub.py            # or: ryu-manager p1_learning.py

   # Parts 2 and 3 (OpenFlow 1.3, need Ryu's LLDP link discovery)
   ryu-manager --observe-links p2_spanning_tree.py
   ryu-manager --observe-links p3_spr.py
   ```

2. Start the topology that came with the assignment and point it at the remote controller. The file and topology names below are placeholders:

   ```bash
   sudo mn --custom <topology>.py --topo <name> \
       --controller=remote,ip=127.0.0.1,port=6653 \
       --switch ovsk,protocols=OpenFlow13        # Parts 2 and 3
   ```

3. In the Mininet CLI, run `pingall`, `dpctl dump-flows` and `iperf h1 h5`.

## Notes

- The Part 3 handout asks for link weights based on capacity. `p3_spr.py` uses measured link delay instead, and the report's algorithm describes the same delay-based approach.
- The report mentions periodically re-measuring delays. In the code, `update_topology()` runs only once because of the `updated_once` flag, so changes made after startup are not picked up. As far as I can tell from the code (I have not run it), that one run starts when the controller launches. It waits about 10 s before reading the topology and about 10 s more for the probe replies, and it drops data packets until it finishes. Start Mininet right after the controller, and wait about 20 s before running `pingall`.
