from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.topology import event
from ryu.topology.api import get_switch, get_link, get_host

class ExampleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ExampleSwitch13, self).__init__(*args, **kwargs)
        self.switches = [] 
        self.topology = {}
        self.links = {}
        self.mac_to_port = {}
        self.spanning_tree = {}
        self.switch_to_openports = {}
    
    def construct_spanning_tree(self):
        visited = set()
        spanning_tree = {}
        root = min(self.topology.keys())
        queue = [root]
        visited.add(root)
        spanning_tree[root] = []

        while queue:
            current = queue.pop(0)
            for neighbor in self.topology[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    out_port, inport = self.links[(current, neighbor)]
                    spanning_tree.setdefault(current, []).append((neighbor, out_port))
                    spanning_tree.setdefault(neighbor, []).append((current, inport))

        self.logger.info(f"Spanning tree: {spanning_tree}")  
        return spanning_tree
    
    @set_ev_cls(event.EventSwitchEnter)
    def get_switches(self, ev):
        self.switches = [switch.dp.id for switch in get_switch(self, None)]
        self.logger.info(f"Switches discovered: {self.switches}")
        
    @set_ev_cls(event.EventLinkAdd)
    def get_links(self, ev):
        self.links = {}
        self.topology = {}
        for link in get_link(self, None):
            src, dst = link.src.dpid, link.dst.dpid
            src_port, dst_port = link.src.port_no, link.dst.port_no

            self.links[(src, dst)] = (src_port, dst_port)
            self.links[(dst, src)] = (dst_port, src_port)

            self.topology.setdefault(src, set()).add(dst)
            self.topology.setdefault(dst, set()).add(src)
              
        if self.switches and self.links:
            self.logger.info("Constructing spanning tree.")
            self.spanning_tree = self.construct_spanning_tree()
            
        self.logger.info(f"{self.topology}")
             
    @set_ev_cls(event.EventHostAdd)
    def host_add_handler(self, ev):
        host = ev.host
        dpid, port_no = host.port.dpid, host.port.port_no
        self.logger.info(f"Connected host MAC({host.mac}) to switch {dpid}, port {port_no}")
        self.switch_to_openports.setdefault(dpid, []).append(port_no)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        self.logger.info("Sent to controller")
        datapath = ev.msg.datapath
        ofproto, parser = datapath.ofproto, datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.flow_addition(datapath, 0, match, actions)

    def flow_addition(self, datapath, priority, match, actions):
        ofproto, parser = datapath.ofproto, datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)
        
    def get_spanning_tree_ports(self, dpid):
        spanning_tree_ports = [port for _, port in self.spanning_tree.get(dpid, [])]
        spanning_tree_ports.extend(self.switch_to_openports.get(dpid, []))
        return spanning_tree_ports

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto, parser = datapath.ofproto, datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        
        if eth.ethertype in (ether_types.ETH_TYPE_LLDP, 0x0026):
            return

        dst, src = eth.dst, eth.src
        self.mac_to_port.setdefault(dpid, {})[src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.flow_addition(datapath, 1, match, actions)
        else:
            actions = [parser.OFPActionOutput(port) 
                       for port in self.get_spanning_tree_ports(dpid) 
                       if port != in_port]
            
            if not actions:
                return

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions, data=msg.data)
        datapath.send_msg(out)