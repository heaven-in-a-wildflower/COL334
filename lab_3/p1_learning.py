# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An OpenFlow 1.0 L2 learning switch implementation.
"""

# Base class for building any Ryu application
from ryu.base import app_manager

# Handle openflow protcol events
from ryu.controller import ofp_event

# MAIN_DISPATCHER is the state where the switch is ready to send or receive instructions
from ryu.controller.handler import MAIN_DISPATCHER

# Decorator for event handlers
from ryu.controller.handler import set_ev_cls

# Specify that openflow version 1.0 will be used 
from ryu.ofproto import ofproto_v1_0

# Convert MAC addresses to binary format 
from ryu.lib.mac import haddr_to_bin

# Handle packet parsing and easy manipulation of packets
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types

# SimpleSwicth inherits the functionality of Ryu controller
class SimpleSwitch(app_manager.RyuApp):

    # Tell the application which version of oopenflow to use
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    # Call constructor of parent class
    def __init__(self, *args, **kwargs):
        super(SimpleSwitch, self).__init__(*args, **kwargs)
        
        # Create forwarding table
        self.mac_to_port = {}

    # This methods adds a flow entry into the flow table
    def add_flow(self, datapath, in_port, dst, src, actions):

        # Gives access to protocol constants??
        ofproto = datapath.ofproto

        # OFPMatch specifies the matching criteria for the flow(incoming port, dst_mac and src_mac) 
        match = datapath.ofproto_parser.OFPMatch(
            in_port=in_port,
            dl_dst=haddr_to_bin(dst),
            dl_src=haddr_to_bin(src))

        # OFPFlowMod creates the flow modification message
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,
            match=match, 
            cookie=0, # Use for flow tracking
            command=ofproto.OFPFC_ADD, # Specify adding a new flow 
            idle_timeout=0, hard_timeout=0, # No timeout for flow => It will stay unil explicitly removed
            priority=ofproto.OFP_DEFAULT_PRIORITY, # Default priority for flow
            flags=ofproto.OFPFF_SEND_FLOW_REM, # Flag to notify the controller when the switch is removed 
            actions=actions # Specify what actions are to be taken for matching flows
        )
        datapath.send_msg(mod) # Send the flow-modification message to the switch

    # set_ev_cls decorator registers _packet_in_handler as the event handler for the event EventOfPacketIn which is triggered when a packet is received that does not match any flow table entry.
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg # Contains packet and related data
        datapath = msg.datapath # Refers to the switch that sent the message 
        ofproto = datapath.ofproto # Contains protocol specific constants

        # Parse the raw packet into structured protocol layers
        pkt = packet.Packet(msg.data)

        # Extract ethernet header from the packet
        eth = pkt.get_protocol(ethernet.ethernet)

        # LLDP(link layer discovery protocol) packets are ignored because they are used for topology discovery and not regular data forwarding
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Source and destination MAC addresses 
        dst = eth.dst
        src = eth.src

        # dpid is the switch's unique identifier
        dpid = datapath.id

        # Ensure that there is an entry for the switch's dpid in mac_to_port dictionary.
        # If there is no such entry, it creates one.
        self.mac_to_port.setdefault(dpid, {})

        # Log info
        self.logger.info("packet in %s %s %s %s", dpid, src, dst, msg.in_port)

        # mac_to_port is a nested dictionary. Its outer key is the dpid of the switch and inner key is the mac_address of the destination. The content is the port no.

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = msg.in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # Specify the action : Send via the out_port 
        actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            # Note the parameters which constitute a flow 
            self.add_flow(datapath, msg.in_port, dst, src, actions)

        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
            actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no

        ofproto = msg.datapath.ofproto
        if reason == ofproto.OFPPR_ADD:
            self.logger.info("port added %s", port_no)
        elif reason == ofproto.OFPPR_DELETE:
            self.logger.info("port deleted %s", port_no)
        elif reason == ofproto.OFPPR_MODIFY:
            self.logger.info("port modified %s", port_no)
        else:
            self.logger.info("Illeagal port state %s %s", port_no, reason)