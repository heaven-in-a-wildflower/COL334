from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.topology.api import get_switch, get_link
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event, switches
from ryu.lib.packet import ethernet, lldp, packet
from ryu.lib import mac, hub
import time
import heapq
from collections import defaultdict, deque

class Graph:
    def __init__(self):
        self.nodes = []
        self.edges = defaultdict(list)
        self.weights = {}

    def add_edge(self, src, dst, weight):
        if src not in self.nodes:
            self.nodes.append(src)
        if dst not in self.nodes:
            self.nodes.append(dst)
        self.edges[src].append(dst)
        self.weights[(src, dst)] = weight

    def dijkstra(self, initial):
        shortest_paths = {initial: (None, 0)}
        visited = set()
        pq = [(0, initial)]

        while pq:
            current_cost, current_node = heapq.heappop(pq)
            if current_node in visited:
                continue
            visited.add(current_node)

            for neighbor in self.edges[current_node]:
                weight = self.weights[(current_node, neighbor)]
                total_cost = current_cost + weight

                if neighbor not in shortest_paths or total_cost < shortest_paths[neighbor][1]:
                    shortest_paths[neighbor] = (current_node, total_cost)
                    heapq.heappush(pq, (total_cost, neighbor))

        return shortest_paths

    def get_next_hops(self):
        print(self.nodes)
        print(self.edges)
        next_hop = {sw: {sw2: None for sw2 in self.nodes} for sw in self.nodes}

        for i in range(len(self.nodes)):
            for j in range(len(self.nodes)):
                if (i==j):
                    continue
                next_hop[self.nodes[i]][self.nodes[j]] = self.get_shortest_path(self.nodes[i], self.nodes[j])

        return next_hop

    def get_shortest_path(self, start, end):
        shortest_paths = self.dijkstra(start)
        path = []
        node = end

        while node is not None:
            path.append(node)
            node = shortest_paths[node][0]
        print(start, end, path[::-1])

        if (len(path) < 2):
            print("ERRORRRRRR")
            return None

        return path[-2]
    
class SpanningTreeCreator:
    def __init__(self):
        self.network = None
        self.spanning_tree = None
        self.non_tree_ports = {}
        self.host_ports = None
        self.logger = None

    def create_spanning_tree(self):
        if not self.network:
            return

        start_switch = min(self.network.keys())
        self.spanning_tree = {switch: None for switch in self.network}
        self.bfs(start_switch)

        self.logger.info(f"Spanning tree created: {self.spanning_tree}")
        for child, parent in self.spanning_tree.items():
            self.logger.info(f"Child: {child}, Parent: {parent}")

        self.identify_non_tree_ports()

    def bfs(self, start_switch):
        queue = deque([start_switch])
        visited = set([start_switch])

        while queue:
            current_switch = queue.popleft()
            for neighbor in self.network[current_switch]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    self.spanning_tree[neighbor] = current_switch

    def identify_non_tree_ports(self):
        for switch in self.network:
            all_ports = set()
            tree_ports = set()
            for neighbor, port_info in self.network[switch].items():
                all_ports.add(port_info)
                if self.spanning_tree.get(neighbor) == switch or self.spanning_tree.get(switch) == neighbor:
                    tree_ports.add(port_info)
            self.non_tree_ports[switch] = all_ports - tree_ports

    def get_spanning_tree_ports(self, switch, in_port):
        tree_ports = set()
        for neighbor, port_info in self.network[switch].items():
            if self.spanning_tree.get(neighbor) == switch or self.spanning_tree.get(switch) == neighbor:
                tree_ports.add(port_info)
        
        tree_ports.update(self.host_ports.get(switch, set()))
        return tree_ports - {in_port}
    
class SPSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SPSwitch, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.switches = []
        self.datapaths = {}
        self.port_map = {}
        self.lldp_sent = {}
        self.switch_dp = {}
        self.next_hop={}
        self.mac_to_port = {} 
        self.mac_to_switch = {}

        self.host_ports = {}
        self.network = {}
        
        self.spt_manager = SpanningTreeCreator()
        self.spt_manager.host_ports = self.host_ports
        self.spt_manager.network = self.network
        self.spt_manager.logger = self.logger

        self.echo_sent = {}
        self.echo_delay = {}
        self.graph = Graph()
        self.updated_once = False
        self.done = False
        self.monitor_thread = hub.spawn(self._monitor)


    def _monitor(self):
        while True:
            self.update_topology()
            hub.sleep(10)

    def get_switch_by_mac(self, mac):
        if mac in self.mac_to_switch:
            return self.mac_to_switch[mac]
        else:
            self.logger.error("MAC %s not found!!", mac)
            return None


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath
        self.send_echo_request(datapath)

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id, priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):
        self.update_topology()

    def update_topology(self):
        if self.updated_once:
            return
        self.updated_once = True

        time.sleep(10)
        switch_list = get_switch(self.topology_api_app, None)
        self.switches = [switch.dp.id for switch in switch_list]
        for switch in switch_list:
            self.switch_dp[switch.dp.id]=switch.dp
        self.network = {s_: {} for s_ in self.switches}
        
        links_list = get_link(self.topology_api_app, None)
        for link in links_list:
            src, dst = link.src.dpid, link.dst.dpid
            self.network[src][dst] = link.src.port_no
            self.network[dst][src] = link.dst.port_no
        print("Network: ")
        print(self.network)
        self.logger.info("List is %s", links_list)

        for link in links_list:
            src, dst = link.src.dpid, link.dst.dpid
            src_port_no = link.src.port_no
            print("src: ", src, "dst: ", dst, "src_port_no: ", src_port_no)
            send_time = self.simulate_lldp_delay(src, dst, src_port_no)
            self.port_map[(src, dst)] = link.src.port_no
            self.port_map[(dst, src)] = link.dst.port_no

        self.detect_host_ports(switch_list, links_list)
        self.spt_manager.network = self.network
        self.spt_manager.create_spanning_tree()
        print(self.spt_manager.spanning_tree)

        time.sleep(10)
        self.next_hop = self.graph.get_next_hops()
        print("next_hop: ",self.next_hop)
        self.done = True


    def build_lldp_packet(self, datapath, port_no):
        timestamp = time.time()
        eth = ethernet.ethernet(
            dst=lldp.LLDP_MAC_NEAREST_BRIDGE,
            src=datapath.ports[port_no].hw_addr,
            ethertype=ethernet.ether.ETH_TYPE_LLDP
        )
        chassis_id = lldp.ChassisID(
            subtype=lldp.ChassisID.SUB_LOCALLY_ASSIGNED,
            chassis_id=str(datapath.id).encode('utf-8')
        )
        port_id = lldp.PortID(
            subtype=lldp.PortID.SUB_PORT_COMPONENT,
            port_id=str(port_no).encode('utf-8')
        )
        print("chassis_id: ",chassis_id,"port_id: ",port_id)
        ttl = lldp.TTL(ttl=120)
        tlv_type = 127
        tlv_value = b"latency_measurement"
        tlv_header = (tlv_type << 9) | len(tlv_value)
        tlv_header_bytes = tlv_header.to_bytes(2, byteorder='big')
        custom_tlv = tlv_header_bytes + tlv_value
        lldp_pkt = lldp.lldp(tlvs=[chassis_id, port_id, ttl])
        pkt = packet.Packet()
        pkt.add_protocol(eth)
        pkt.add_protocol(lldp_pkt)
        pkt.serialize()
        pkt.data += custom_tlv

        return pkt

    def send_lldp_packet(self, datapath, port_no, pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        pkt_data = pkt.data
        actions = [parser.OFPActionOutput(port_no)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt_data
        )
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        pkt = packet.Packet(msg.data)
        if self.is_our_lldp_packet(pkt,msg):
            src = datapath.id
            in_port = msg.match['in_port']
            src_port_no = in_port
            dst = pkt.get_protocol(lldp.lldp).tlvs[0].chassis_id.decode('utf-8')
            dst = int(dst)

            if (src, src_port_no) in self.lldp_sent:
                send_time = self.lldp_sent.pop((src, src_port_no))
                rec_time = time.time()
                round_trip_delay = rec_time - send_time
                if round_trip_delay - 2* self.echo_delay[datapath.id] > 0:
                    round_trip_delay -= 2* self.echo_delay[datapath.id]
                self.logger.info("LLDP delay from %s to %s: %f seconds", src, dst, round_trip_delay)
                rounded_off_delay=round(round_trip_delay,4)
                self.graph.add_edge(src, dst, rounded_off_delay)
                self.graph.add_edge(dst, src, rounded_off_delay)
            return

        if not self.done:
            return

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == 0x88cc:
            return
        
        src = eth.src
        dst = eth.dst
        
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        self.logger.info("Packet in: %s %s %s %s", dpid, src, dst, in_port)

        if src not in self.mac_to_switch:
            self.mac_to_switch[src] = dpid

        if dst not in self.mac_to_port[dpid]:
            self.spt_manager.host_ports = self.host_ports
            self.spt_manager.network = self.network
            self.spt_manager.logger = self.logger

            tree_ports = self.spt_manager.get_spanning_tree_ports(dpid, in_port)
            self.logger.info(f"Broadcasting to ports: {tree_ports} on switch {dpid}")
            actions = []
            for port in tree_ports:
                actions.append(parser.OFPActionOutput(port))

            out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port, actions=actions, data=msg.data)
            datapath.send_msg(out)
            return

        dst_switch = self.mac_to_switch[dst]
        src_switch = dpid

        if src_switch == dst_switch:
            out_port = self.mac_to_port[dst_switch][dst]
        else:
            self.logger.info(f"Next hop: {self.next_hop}")
            next_hop_switch = self.next_hop[src_switch][dst_switch]
            out_port = self.port_map[(src_switch, next_hop_switch)]
        
        actions = [parser.OFPActionOutput(out_port)]
        match = parser.OFPMatch(eth_dst=dst, eth_src=src)

        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            self.add_flow(datapath, 1, match, actions, msg.buffer_id)
        else:
            self.add_flow(datapath, 1, match, actions)
        
        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id,
            in_port=in_port, actions=actions, data=msg.data)
        datapath.send_msg(out)

    def send_echo_request(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        echo_req = parser.OFPEchoRequest(datapath, data=b'echo_data')
        send_time = time.time()
        self.echo_sent[datapath.id] = send_time
        datapath.send_msg(echo_req)
        self.logger.info("Echo to switch %s at time: %f", datapath.id, send_time)

    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def _echo_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        receiver_time = time.time()

        if datapath.id in self.echo_sent:
            sender_time = self.echo_sent.pop(datapath.id)
            one_way_delay = (receiver_time - sender_time) / 2
            
            self.logger.info("Estimated controller-switch delay %s: %f seconds", datapath.id, one_way_delay)
            self.echo_delay[datapath.id] = one_way_delay
        
    def simulate_lldp_delay(self, src, dst, port_no):
        src_datapath = self.switch_dp[src]
        dst_datapath = self.switch_dp[dst]
        if src_datapath and dst_datapath:
            lldp_pkt = self.build_lldp_packet(src_datapath, port_no)
            send_time = time.time()
            self.lldp_sent[(src, port_no)] = send_time
            self.send_lldp_packet(src_datapath, port_no, lldp_pkt)
            return send_time
        return 0

    def is_our_lldp_packet(self, pkt, msg):
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        if eth_pkt.ethertype == 0x88CC:
            lldp_pkt = pkt.get_protocol(lldp.lldp)
            custom_tlv = msg.data[-len("latency_measurement") - 2:]
            custom_tlv_type = (custom_tlv[0] >> 1)
            custom_tlv_value = custom_tlv[2:].decode()
            if custom_tlv_type == 127:
                if custom_tlv_value == "latency_measurement":
                    return True
        return False

    def detect_host_ports(self, switch_list, links_list):
        switch_ports = set((link.src.dpid, link.src.port_no) for link in links_list)
        switch_ports.update((link.dst.dpid, link.dst.port_no) for link in links_list)

        self.host_ports = {}
        for switch in switch_list:
            dpid = switch.dp.id
            ports = set([p.port_no for p in switch.ports])
            self.host_ports[dpid] = ports - {port for _, port in switch_ports}
            self.logger.info(f"Host ports on switch {dpid}: {self.host_ports[dpid]}")