# Import necessary libraries
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types

class SimpleHub(app_manager.RyuApp):

    # Use OpenFlow 1.0
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleHub, self).__init__(*args, **kwargs)

    # This function floods packets to all ports except the incoming one
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Parse the incoming packet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignore LLDP packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Extract the destination and source MAC addresses
        dst = eth.dst
        src = eth.src

        # Log packet info
        dpid = datapath.id
        self.logger.info("packet in dpid:%s src:%s dst:%s in_port:%s", dpid, src, dst, msg.in_port)

        # Set the output port to FLOOD (floods to all ports except the receiving one)
        out_port = ofproto.OFPP_FLOOD

        # Define actions (send the packet to all ports except the incoming one)
        actions = [parser.OFPActionOutput(out_port)]

        # If the switch has no buffer for the message, the data needs to be explicitly included in the output message
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Send the PacketOut message to flood the packet
        out = parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)
