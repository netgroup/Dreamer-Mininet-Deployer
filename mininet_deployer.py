#!/usr/bin/python

##############################################################################################
# Copyright (C) 2014 Pier Luigi Ventre - (Consortium GARR and University of Rome "Tor Vergata")
# Copyright (C) 2014 Giuseppe Siracusano, Stefano Salsano - (CNIT and University of Rome "Tor Vergata")
# www.garr.it - www.uniroma2.it/netgroup - www.cnit.it
#
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Mininet Deployer.
#
# @author Pier Luigi Ventre <pl.ventre@gmail.com>
# @author Giuseppe Siracusano <a_siracusano@tin.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#
#

from mininet.net import Mininet
import time
from mininet.cli import CLI
from mininet.node import RemoteController, Node, OVSKernelSwitch
from mininet.link import Link

from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel, info, debug
from mininet.log import lg
from topo_parser import TopoParser

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt


from oshi import *
from deployer_utils import *
from deployer_net_utils import *
from deployer_configuration_utils import *

from functools import partial
import subprocess
import os
import shutil
import sys
import argparse


aoshis = []
oshis = []
nets = []
switches = []
L2nets = []
ctrls = []
hosts = []

# XXX Parameter 
# Vll path
vll_path = "" #"../vll_pusher_for_floodlights/"
# Executable path
path_quagga_exec = "" #"/usr/lib/quagga/"

# Controller Parameter
ctrls_ip = ['192.168.0.1']
ctrls_port = [6633]

# Parameter Coexistence Core Approach
CORE_APPROACH = 'A' # It can be A or B

# XXX Virtual Leased Line Configuration
LHS_tunnel = ['euh1', "euh2"]
RHS_tunnel = ['euh3', "euh1"]
tunnels = []
LHS_tunnel_aoshi = []
RHS_tunnel_aoshi = []
LHS_tunnel_port = []
RHS_tunnel_port = []
LHS_tunnel_vlan = []
RHS_tunnel_vlan = []
TRUNK_TO_TAG = {}
ACCESS_TO_TAG = {}
AOSHI_TO_TAG = {}

verbose = True
	  		
def check_tunnel_configuration():
	for i in range(0,len(LHS_tunnel)):
		host1 = LHS_tunnel[i]
		host2 = RHS_tunnel[i]
		if host1 not in hosts or host2 not in hosts:
			print "Error Misconfiguration Virtual Leased Line"
			print "Error Cannot Connect", host1, "To", host2
			sys.exit(2)


def SDN_tunnel_setup_oneside(net, side):
	global LHS_tunnel_aoshi
	global RHS_tunnel_aoshi
	global LHS_tunnel_port
	global RHS_tunnel_port
	global LHS_tunnel_vlan
	global RHS_tunnel_vlan
	k = 0
	if side == 'LHS':
		side_tunnel = LHS_tunnel
	else:
		side_tunnel = RHS_tunnel
	for host in side_tunnel:
		print "*** SDN Setup For", host
		nextHop = None
		i = 0
		while host not in L2nets[i].Nodes:
			i = i + 1
		if i == len(L2nets):
			print "Configuration Error"
			print "Cannot Find The Host", host
			sys.exit(-2)
		print "*** %s" % host, "is in %s" % L2nets[i].name
		done = False
		currentNode = host
		aoshi = L2nets[i].getAoshi(host)
		if side == 'RHS' and aoshi[0] == LHS_tunnel_aoshi[k] and aoshi[2] == LHS_tunnel_port[k]:
			print "*** Internal Tunnel"
			value = LHS_tunnel_vlan[k]
			tag = value
		else: 
			default = 2
			# The Aoshi's link is the RHS
			value = AOSHI_TO_TAG.get(aoshi[2], default)
			tag = value
			AOSHI_TO_TAG[aoshi[2]] = value + 1
		print "*** VLAN Tag", tag
		while done == False:
			nextNode = L2nets[i].getNextHop(currentNode)
			if 'euh' in currentNode and 'sw' in nextNode[0]:
				rhs_new_link = net.getNodeByName(nextNode[0])				
				lhs_new_link = net.getNodeByName(currentNode)
				l = net.addLink(lhs_new_link, rhs_new_link)
				tunnels[k].add_intf(l.intf1.name)
				# l.intf1 contains the NextHop's new port
				ACCESS_TO_TAG[l.intf2.name] = str(tag) + ","
				z = 0
				for network in nets:
					if len(network.belong(currentNode)) > 0:
						break
					z  = z + 1
				if z == len(nets):
					print "Configuration Error"
					print "Cannot Find The Host", currentNode, "In The OSPF Networks"
					sys.exit(-2)
				network.append_intf(l.intf1.name)
				currentNode = nextNode[0]
			elif 'sw' in currentNode:
				# NextNode[1] contains the currentNode's port
				default = ""
				tags = (TRUNK_TO_TAG.get(nextNode[1], default)).split(',')
				if str(tag) not in tags:
					TRUNK_TO_TAG[nextNode[1]] = TRUNK_TO_TAG.get(nextNode[1], default) + str(tag) + ","
				if 'aos' in nextNode[0]:
					aoshi = net.getNodeByName(nextNode[0])
					if side == 'LHS':
						LHS_tunnel_aoshi.append(aoshi.name)
						LHS_tunnel_port.append(nextNode[2])
						LHS_tunnel_vlan.append(tag)
					else:
						RHS_tunnel_aoshi.append(aoshi.name)
						RHS_tunnel_port.append(nextNode[2])
						RHS_tunnel_vlan.append(tag)
					done = True
				elif 'sw' in nextNode[0]:
					# NextNode[1] contains the nextHop's port
					tags = (TRUNK_TO_TAG.get(nextNode[2], default)).split(',')
					if str(tag) not in tags:
						TRUNK_TO_TAG[nextNode[2]] = TRUNK_TO_TAG.get(nextNode[2], default) + str(tag) + ","
				currentNode = nextNode[0]
			else:
				print "Error In The Network Configuration"
				print "Tunnel Setup Cannot Work Properly"
				sys.exit(-2)
		k = k + 1

def SDN_tunnel_setup(net):
	print "*** L2 Access Networks SDN Setup"
	print "*** SDN Setup For LHS"
	SDN_tunnel_setup_oneside(net, 'LHS')
	print "*** SDN Setup For RHS"
	SDN_tunnel_setup_oneside(net, 'RHS')
		
def IP_tunnel_setup():
	print "*** L2 Access Networks IP Setup"
	for host in hosts:
		print "*** IP Setup For", host
		nextHop = None
		i = 0
		while host not in L2nets[i].Nodes:
			i = i + 1
		if i == len(L2nets):
			print "Configuration Error"
			print "Cannot Find The Host", host
			sys.exit(-2)
		print "*** %s" % host, "is in %s" % L2nets[i].name
		done = False
		currentNode = host
		tag = L2nets[i].VlanIP
		while done == False:
			nextNode = L2nets[i].getNextHop(currentNode)
			if 'euh' in currentNode and 'sw' in nextNode[0]:
				# NextNode[1] contains the Link's LHS
				# ACCESS PORT is the RHS
				ACCESS_TO_TAG[nextNode[2]] = tag + ","
				currentNode = nextNode[0]
			elif 'sw' in currentNode:
				# NextNode[1] contains the Link's LHS
				default = ""
				tags = (TRUNK_TO_TAG.get(nextNode[1], default)).split(',')
				if tag not in tags:
					TRUNK_TO_TAG[nextNode[1]] = TRUNK_TO_TAG.get(nextNode[1], default) + tag + ","
				if 'aos' in nextNode[0]:
					done = True
				elif 'sw' in nextNode[0]:
					tags = (TRUNK_TO_TAG.get(nextNode[2], default)).split(',')
					if tag not in tags:
						TRUNK_TO_TAG[nextNode[2]] = TRUNK_TO_TAG.get(nextNode[2], default) + tag + ","
				currentNode = nextNode[0]
			else:
				print "Error In The Network Configuration"
				print "Tunnel Setup Cannot Work Properly"
				sys.exit(-2)

def configure_l2_accessnetwork():
	print "*** Configure L2 Access Networks"
	root = Node( 'root', inNamespace=False )
	print "*** Configure L2 Access Ports" 
	for key, value in ACCESS_TO_TAG.iteritems():
		print "*** Configure", key, "As Access Port, TAG=", value
		root.cmd("ovs-vsctl set port %s tag=%s" %(key, value))
	print "*** Configure L2 Trunk Ports"
	for key, value in TRUNK_TO_TAG.iteritems():
		print "*** Configure", key, "As Trunk Port, TAG=", value
		root.cmd("ovs-vsctl set port %s trunks=%s" %(key, value))
			
def create_access_network(net):
	print "*** Create Access Networks"
	global nets
	global oshis
	global aoshis
	OSHI = len(oshis)
	for i in range(OSHI, (2*OSHI)):
		aoshi = (net.addHost('aos%s' % (i+1), loopback = give_me_next_loopback()))
		l = net.addLink(aoshi, oshis[i % OSHI])
		nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
		print "*** Connect", aoshi, "To", oshis[i % OSHI]
		create_l2_access_network(aoshi, net)   
		aoshis.append(aoshi)

def create_l2_access_network(aoshi, net, n_host=1):
	global switches
	global hosts
	global L2nets
	name = "L2AccessNetwork" + str(len(L2nets) + 1);
	l2net = L2AccessNetwork(name, classification = 'B')
	print "*** Create L2 Access Network For", aoshi.name
	intfs = []
	hosts_in_rn = []
	print "*** Create L2 Switch"
	next = len(switches)
	sw = net.addSwitch("sw%s" % (next+1))
	print "*** Create Switch", sw.name
	hosts_in_rn.append(sw)
	l = net.addLink(sw, aoshi)
	print "*** Connect", sw, "To", aoshi
	l2net.addLink(l)
	intfs.append(l.intf2.name)
	switches.append(sw)

	# Create Another L2 Switch
	# temp = sw
	# next = len(switches)
	# print "*** Create Switch", sw.name
	# sw = net.addSwitch("sw%s" % (next+1))
	# hosts_in_rn.append(sw)
	# l = net.addLink(sw, temp)
	# print "*** Connect", sw, "To", temp
	# l2net.addLink(l)
	# switches.append(sw)

	print "*** Create End User Hosts"
	for i in range(len(hosts), (len(hosts) + n_host)):
		host = net.addHost(('euh%s') % (i+1), loopback = "0.0.0.0")
		l = net.addLink(host,sw)
		l2net.addLink(l)
		print "*** Connect", host, "To", sw
		hosts.append(host.name)
		intfs.append(l.intf1.name)
	nets.append(OSPFNetwork(intfs, ctrl=False, hello_int=2))
	fixIntf(hosts_in_rn)
	L2nets.append(l2net)

def buildTopoFromFile(param):
	global oshis
	global aoshis
	global switches
	global hosts
	global ctrls

	if verbose:
		print "*** Build Topology From Parsed File"
	parser = TopoParser(param, verbose=False)
	(ppsubnets, l2subnets) = parser.getsubnets()
	set_oshis = parser.oshis
	set_aoshis = parser.aoshis
	set_l2sws = parser.l2sws
	set_euhs = parser.euhs
	hosts_in_rn = []
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=OSHI, build=False )
	if verbose:
		print "*** Build OSHI"	
	for oshi in set_oshis:
		osh = net.addHost(oshi, loopback = give_me_next_loopback())
		oshis.append(osh)
	if verbose:
		print "*** Build AOSHI"
	for aoshi in set_aoshis:
		aos = net.addHost(aoshi, loopback = give_me_next_loopback())
		aoshis.append(aos)
	if verbose:
		print "*** Build L2SWS"
	for l2sw in set_l2sws:
		sw = net.addSwitch(l2sw)
		switches.append(sw)
		hosts_in_rn.append(sw)
	if verbose:
		print "*** Build EUHS"
	for euh in set_euhs:
		net.addHost(euh, loopback = "0.0.0.0")
		hosts.append(euh)	
	if verbose:	
		print "*** Create Core Networks Point To Point"
	i = 0
	for ppsubnet in ppsubnets:
		if ppsubnet.type == "CORE":
			if verbose:
				print "*** Subnet: Node %s - Links %s" %(ppsubnet.nodes, ppsubnet.links)
			node1 = net.getNodeByName(ppsubnet.links[0][0])
			node2 = net.getNodeByName(ppsubnet.links[0][1])
			l = net.addLink(node1, node2)
			nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
			if verbose:			
				print "*** Connect", node1.name, "To", node2.name
		i = i + 1
	if verbose:	
		print "*** Create Core Networks Switched"
	for l2subnet in l2subnets:
		if l2subnet.type == "CORE":
			if verbose:
				print "*** Subnet: Node %s - Links %s" % (ppsubnet.nodes, ppsubnet.links)
			intfs = []
			for link in l2subnet.links:
				node1 = net.getNodeByName(link[0])
				node2 = net.getNodeByName(link[1])
				l = net.addLink(node1, node2)
				if verbose:			
					print "*** Connect", node1.name, "To", node2.name
				if 'sw' not in link[0] and 'sw' in link[1]:
					intfs.append(l.intf1.name)
				elif 'sw' in link[0] and 'sw' not in link[1]:
					intfs.append(l.intf2.name)
				elif 'sw' in link[0] and 'sw' in link[1]:
					continue
				else:
					print "Error Switched Networks - Both EndPoint != SW"
					sys.exit(-2)
			nets.append(OSPFNetwork(intfs, ctrl=False))
		i = i + 1
	if verbose:	
		print "*** Create Access Networks Point To Point"
	i = 0
	for ppsubnet in ppsubnets:
		if ppsubnet.type == "ACCESS":
			# XXX The Order now is important
			"""if verbose:
				print "*** Subnet: Node %s - Links %s" %(ppsubnet.nodes, ppsubnet.links)
			node1 = net.getNodeByName(ppsubnet.links[0][0])
			node2 = net.getNodeByName(ppsubnet.links[0][1])
			l = net.addLink(node1, node2)
			nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
			if verbose:			
				print "*** Connect", node1.name, "To", node2.name"""
			print "Error Not Managed For Now"
			sys.exit(-2)
		i = i + 1
	if verbose:	
		print "*** Create Acces Networks Switched"
	for l2subnet in l2subnets:
		if l2subnet.type == "ACCESS":
			name = "L2AccessNetwork" + str(len(L2nets) + 1);
			l2net = L2AccessNetwork(name, classification = 'B')
			if verbose:
				print "*** Subnet: Node %s - Links %s" % (l2subnet.nodes, l2subnet.links)
				print "*** Create L2 Access Network - Classification", l2net.classification	
			intfs = []
			# XXX The Order now is important
			ord_links = l2subnet.getOrderedLinks()
			for link in ord_links:
				node1 = net.getNodeByName(link[0])
				node2 = net.getNodeByName(link[1])
				l = net.addLink(node1, node2)
				l2net.addLink(l)
				if verbose:			
					print "*** Connect", node1.name, "To", node2.name
				if 'sw' not in link[0] and 'sw' in link[1]:
					intfs.append(l.intf1.name)
				elif 'sw' in link[0] and 'sw' not in link[1]:
					intfs.append(l.intf2.name)
				elif 'sw' in link[0] and 'sw' in link[1]:
					continue
				else:
					print "Error Switched Networks - Both EndPoint != SW"
					sys.exit(-2)
			nets.append(OSPFNetwork(intfs, ctrl=False))
			L2nets.append(l2net)
		i = i + 1	
	
	print "*** Creating controller"
	c1 = RemoteController( 'c1', ip=ctrls_ip[0], port=ctrls_port[0])
	ctrls.append(c1)
	hosts_in_rn.append(c1)

	# Connect the controller to the network
	print "*** Connect", osh.name, "To Controller"
	l = net.addLink(osh, c1)
	nets.append(OSPFNetwork(intfs=[l.intf1.name, l.intf2.name], ctrl=True))
	
	# Only needed for hosts in root namespace
	fixIntf(hosts_in_rn)

	# Utility function		
	check_tunnel_configuration()
	
	for i in range(0, len(LHS_tunnel)):
		tunnels.append(Tunnel())

	print "*** Tunnels LHS:", LHS_tunnel
	print "*** Tunnels RHS:", RHS_tunnel

	# Tunnels Setup
	IP_tunnel_setup()
	SDN_tunnel_setup(net)

	i = 0
	for tunnel in tunnels :	
		print "*** Tunnel %d, Subnet %s.%s.%s.%s, Intfs %s" % (i+1, tunnel.subnet[0], tunnel.subnet[1], tunnel.subnet[2], 0, tunnel.intfs)
		i = i + 1

	i = 0
	for l2net in L2nets:
		print "***", l2net.name
		print "*** Nodes:", l2net.Nodes
		print "*** Links:", l2net.Links
		print "*** Intfs:", l2net.intfs
		i = i + 1
	
	print "*** AOSHI Tag:", AOSHI_TO_TAG
	print "*** Trunk Port Configuration:", TRUNK_TO_TAG
	print "*** Access Port Configuration:", ACCESS_TO_TAG
	print "*** LHS AOSHI:", LHS_tunnel_aoshi
	print "*** RHS AOSHI:", RHS_tunnel_aoshi
	print "*** LHS Port:", LHS_tunnel_port
	print "*** RHS Port:", RHS_tunnel_port


	for network in nets:
		print "*** OSPF Network: %s.%s.%s.%s" % (network.subnet[0], network.subnet[1], network.subnet[2], 0), str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int
	return net
	
def Mesh(OSHI_n=4):
	global ctrls
	global oshis
	global aoshis
	global SDN_PORTS
	global TUNNEL_SETUP
	"Create A Mesh Topo"
	print "*** Mesh With", OSHI_n, "OSHI"
	"Creating OSHI"
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=OSHI, build=False )
	i = 0
	h = 0
	print "*** Create Core Networks"
	for i in range(OSHI_n):
		oshi = (net.addHost('osh%s' % (i+1), loopback = give_me_next_loopback()))
		for rhs in oshis:
			l = net.addLink(oshi, rhs)
			nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
			print "*** Connect", oshi, "To", rhs   
		oshis.append(oshi)

	print "*** Creating controller"
	#c0 = net.addController( 'c0', ip=ctrl_root_ip, port=ctrl_root_port )
	c1 = RemoteController( 'c1', ip=ctrls_ip[0], port=ctrls_port[0])
	ctrls.append(c1)
	
	hosts_in_rn = []
	hosts_in_rn.append(c1)
	# Connect the controller to the network
	print "*** Connect", oshi.name, "To Controller"
	l = net.addLink(oshi, c1)
	nets.append(OSPFNetwork(intfs=[l.intf1.name, l.intf2.name], ctrl=True))
	
	# Only needed for hosts in root namespace
	fixIntf(hosts_in_rn)
	
	# Utility function
	create_access_network(net)

	# Utility function		
	check_tunnel_configuration()
	
	for i in range(0, len(LHS_tunnel)):
		tunnels.append(Tunnel())

	print "*** Tunnels LHS:", LHS_tunnel
	print "*** Tunnels RHS:", RHS_tunnel

	# Tunnels Setup
	IP_tunnel_setup()
	SDN_tunnel_setup(net)

	i = 0
	for tunnel in tunnels :	
		print "*** Tunnel %d, Subnet %s.%s.%s.%s, Intfs %s" % (i+1, tunnel.subnet[0], tunnel.subnet[1], tunnel.subnet[2], 0, tunnel.intfs)
		i = i + 1

	i = 0
	for l2net in L2nets:
		print "***", l2net.name
		print "*** Nodes:", l2net.Nodes
		print "*** Links:", l2net.Links
		print "*** Intfs:", l2net.intfs
		i = i + 1
	
	print "*** AOSHI Tag:", AOSHI_TO_TAG
	print "*** Trunk Port Configuration:", TRUNK_TO_TAG
	print "*** Access Port Configuration:", ACCESS_TO_TAG
	print "*** LHS AOSHI:", LHS_tunnel_aoshi
	print "*** RHS AOSHI:", RHS_tunnel_aoshi
	print "*** LHS Port:", LHS_tunnel_port
	print "*** RHS Port:", RHS_tunnel_port
	for network in nets:
		print "*** OSPF Network: %s.%s.%s.%s" % (network.subnet[0], network.subnet[1], network.subnet[2], 0), str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int
	return net

def erdos_renyi_from_nx(n, p):
	g = nx.erdos_renyi_graph(n,p)
	global ctrls
	global oshis
	global aoshis
	global SDN_PORTS
	global TUNNEL_SETUP
	"Create An Erdos Reny Topo"
	"Creating OSHI"
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=OSHI, build=False )
	i = 0
	h = 0
	# This is the basic behavior, with nx we create only the core network
	for n in g.nodes():
		n = n + 1
		oshi = (net.addHost('osh%s' % (n), loopback = give_me_next_loopback()))
		oshis.append(oshi)
	for (n1, n2) in g.edges():
		n1 = n1 + 1
		n2 = n2 + 1
		lhs = net.getNodeByName('osh%s' % n1)
		rhs = net.getNodeByName('osh%s' % n2)
		l = net.addLink(lhs, rhs)
		nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
		print "*** Connect", lhs, "To", rhs 

	hosts_in_rn = []
	c1 = RemoteController( 'c1', ip=ctrls_ip[0], port=ctrls_port[0])
	ctrls.append(c1)
	hosts_in_rn.append(c1)

	# Connecting the controller to the network 
	print "*** Connect %s" % oshi," To c1"
	l = net.addLink(oshi, c1)
	nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=True, hello_int=5))
	
	# Only needed for hosts in root namespace
	fixIntf(hosts_in_rn)
	
	# Utility function
	create_access_network(net)

	# Utility function		
	check_tunnel_configuration()
	
	for i in range(0, len(LHS_tunnel)):
		tunnels.append(Tunnel())

	print "*** Tunnels LHS:", LHS_tunnel
	print "*** Tunnels RHS:", RHS_tunnel

	# Tunnels Setup
	IP_tunnel_setup()
	SDN_tunnel_setup(net)

	i = 0
	for tunnel in tunnels :	
		print "*** Tunnel %d, Subnet %s.%s.%s.%s, Intfs %s" % (i+1, tunnel.subnet[0], tunnel.subnet[1], tunnel.subnet[2], 0, tunnel.intfs)
		i = i + 1

	i = 0
	for l2net in L2nets:
		print "***", l2net.name
		print "*** Nodes:", l2net.Nodes
		print "*** Links:", l2net.Links
		print "*** Intfs:", l2net.intfs
		i = i + 1
	
	print "*** AOSHI Tag:", AOSHI_TO_TAG
	print "*** Trunk Port Configuration:", TRUNK_TO_TAG
	print "*** Access Port Configuration:", ACCESS_TO_TAG
	print "*** LHS AOSHI:", LHS_tunnel_aoshi
	print "*** RHS AOSHI:", RHS_tunnel_aoshi
	print "*** LHS Port:", LHS_tunnel_port
	print "*** RHS Port:", RHS_tunnel_port


	for network in nets:
		print "*** OSPF Network: %s.%s.%s.%s" % (network.subnet[0], network.subnet[1], network.subnet[2], 0), str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int

	# We generate the topo's png
	pos = nx.circular_layout(g)
        nx.draw(g, pos)
        plt.savefig("topo.png")

	return net

def buildTopoFromNx(topo, args):
	if topo == 'e_r':
		data = args.split(",")
		args = []
		args.append(int(data[0]))
		args.append(float(data[1]))
		if len(args) >= 2:
			if args [0] > 10 or args[1] > 1:
				print "Warning Parameter Too High For Erdos Renyi", "Nodes %s" % args[0], "Interconnection Probability %s" % args[1]
				print "Using Default Parameter"
				args[0] = 5
				args[1] = 0.8
		else :
			args[0] = 5
			args[1] = 0.8
		print "Erdos Renyi", "Nodes %s" % args[0], "Interconnection Probability %s" % args[1]
		return erdos_renyi_from_nx(args[0], args[1])

	print "Error NX Wrong Parameter"
	sys.exit(-2) 		

def configure_env_oshi(oshi):
	global next_ctrl
	print "*** Configuring Environment For", oshi.name
	shutil.rmtree("/tmp/" + oshi.name, ignore_errors=True)
	os.mkdir("/tmp/" + oshi.name)
	ctrl_ip = ctrls_ip[next_ctrl]
	ctrl_port = ctrls_port[next_ctrl]
	next_ctrl = (next_ctrl + 1) % len(ctrls_ip)
	configure_ovs(oshi, ctrl_ip, ctrl_port)
	configure_quagga(oshi)
	oshi.cmd("echo 1 > /proc/sys/net/ipv4/ip_forward ")
	oshi.cmd("echo 0 > /proc/sys/net/ipv4/conf/all/rp_filter") 
	for intf in oshi.nameToIntf:
		cmd = "echo 0 > /proc/sys/net/ipv4/conf/" + intf + "/rp_filter"
		oshi.cmd(cmd)
		intf = "vi%s" % (strip_number(intf))
		if CORE_APPROACH == 'A':
			VLAN_IP = 1 
			intf = intf + "." + str(VLAN_IP)	
		cmd = "echo 0 > /proc/sys/net/ipv4/conf/" + intf + "/rp_filter"
		oshi.cmd(cmd)

def configure_env_ctrl(ctrl):
	global next_ctrl
	print "*** Configuring Environment For Controller", ctrl.name
	shutil.rmtree("/tmp/" + ctrl.name, ignore_errors=True)
	os.mkdir("/tmp/" + ctrl.name)
	configure_quagga(ctrl)
	ctrl.cmd("echo 1 > /proc/sys/net/ipv4/ip_forward ")
	ctrl.cmd("echo 0 > /proc/sys/net/ipv4/conf/all/rp_filter") 
	for intf in ctrl.nameToIntf:
		cmd = "echo 0 > /proc/sys/net/ipv4/conf/" + intf + "/rp_filter"
		ctrl.cmd(cmd)

def configure_node(node):
	print "*** Configuring", node.name
	strip_ip(node)
	for net in nets:
		intfs_to_conf = net.belong(node.name)
		if(len(intfs_to_conf) > 0):
			for intf_to_conf in intfs_to_conf:
				sdn = False
				for tunnel in tunnels:
					if tunnel.belong(intf_to_conf) != None:
						sdn = True
						break
				if sdn == False:
					ip = net.give_me_next_ip()
					gw_ip = "%s.%s.%s.%s" % (net.subnet[0], net.subnet[1], net.subnet[2], 1)
					intf = intf_to_conf
					node.cmd('ip addr add %s/%s brd + dev %s' %(ip, ip_netbit, intf))
					node.cmd('ip link set %s up' % intf)
					node.cmd('route add default gw %s %s' %(gw_ip, intf))
				else:
					ip = tunnel.give_me_next_ip()
					intf = intf_to_conf
					node.cmd('ip addr add %s/%s brd + dev %s' %(ip, sdn_netbit, intf))
					node.cmd('ip link set %s up' % intf)

def configure_ovs(oshi, ctrl_ip, ctrl_port):
	print "*** Configuring OVS For", oshi.name
	path_ovs = "/tmp/" + oshi.name + "/ovs"
	os.mkdir(path_ovs)
	oshi.cmd("ovsdb-tool create " + path_ovs + "/conf.db")
	oshi.cmd("ovsdb-server " + path_ovs + "/conf.db --remote=punix:" + path_ovs + "/db.sock --remote=db:Open_vSwitch,manager_options" +
	" --no-chdir --unixctl=" + path_ovs + "/ovsdb-server.sock --detach")
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait init")
	oshi.cmd("ovs-vswitchd unix:" + path_ovs + "/db.sock -vinfo --log-file=" + path_ovs + "/ovs-vswitchd.log --no-chdir --detach")
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait add-br br-" + oshi.name)

	# Talking with controller
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait set-fail-mode br-" + oshi.name + " secure")
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait set-controller br-" + oshi.name + " tcp:%s:%s" %(ctrl_ip, ctrl_port)) 
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait set controller br-" + oshi.name + " connection-mode=out-of-band")

	# Setting DPID	
	oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait -- set Bridge br-" + oshi.name + " other_config:datapath-id=" + oshi.dpid )

	eth_ports = []
	vi_ports = []
	n_ports = 1
	for intf in oshi.nameToIntf:
		if 'lo' not in intf:		
			oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait add-port br-" + oshi.name + " " + intf)
			eth_ports.append(n_ports)
			n_ports = n_ports + 1
			viname = "vi%s" % strip_number(intf)
			oshi.cmd("ovs-vsctl --db=unix:" + path_ovs + "/db.sock --no-wait add-port br-" + oshi.name + " " + viname
			+ " -- set Interface " + viname + " type=internal")
			vi_ports.append(n_ports)
			n_ports = n_ports + 1
	if CORE_APPROACH == 'A':
		conf_flows_vlan_approach(oshi, eth_ports, vi_ports)
	elif CORE_APPROACH =='B':
		conf_flow_no_vlan_approach(oshi, eth_ports, vi_ports)

	if 'aos' in oshi.name:
		for i in range(0, len(L2nets)):
			intfs = L2nets[i].belong(oshi.name)
			if len(intfs) > 2 :
				print "Error More Than One AOSHI Interface In The Same Subnet"
				sys.exit(-2)
			if len(intfs) == 1 :
				print "*** Configuring Ingress/Egress Rules For %s In Network %s" % (oshi, L2nets[i].name)
				if L2nets[i].classification == 'A':
					conf_flows_ingress_egress_vlan_approach(oshi, i, intfs[0])
				elif L2nets[i].classification == 'B':
					conf_flows_ingress_egress_no_vlan_approach(oshi, i, intfs[0])

def conf_flows_ingress_egress_vlan_approach(oshi, i, intf):
	if CORE_APPROACH == 'A':
		print "*** Already Done Same Approach Between Core And Access"
	elif CORE_APPROACH == 'B':
		print "*** Add Rules For Vlan Access Approach"
		VLAN_IP = L2nets[i].VlanIP	
		eth_intf = intf
		eth_port_number = convert_port_name_to_number(oshi, eth_intf)
		vi_intf = "vi%s" % strip_number(eth_intf)
		vi_port_number = convert_port_name_to_number(oshi, vi_intf)
		oshi.cmd("ovs-ofctl add-flow br-%s \"table=0,hard_timeout=0,priority=300,in_port=%s,dl_vlan=%s,actions=strip_vlan,resubmit(,1)\"" % (oshi.name, eth_port_number,VLAN_IP))
		oshi.cmd("ovs-ofctl add-flow br-%s \"table=1,hard_timeout=0,priority=300,in_port=%s,actions=mod_vlan_vid:%s,output:%s\"" % (oshi.name,vi_port_number,VLAN_IP,eth_port_number))

def conf_flows_ingress_egress_no_vlan_approach(oshi, i, intf):
	if CORE_APPROACH == 'B':
		print "*** Already Done Same Approach Between Core And Access"
	elif CORE_APPROACH == 'A':
		print "*** Add Rule For No Vlan Access Approach"
		VLAN_IP = 1 # Core Vlan	
		eth_intf = intf
		eth_port_number = convert_port_name_to_number(oshi, eth_intf)
		vi_intf = "vi%s" % strip_number(eth_intf)
		vi_port_number = convert_port_name_to_number(oshi, vi_intf)
		oshi.cmd("ovs-ofctl del-flows br-%s in_port=%s,dl_vlan=%s" % (oshi.name,eth_port_number,VLAN_IP))
		oshi.cmd("ovs-ofctl add-flow br-%s hard_timeout=0,priority=300,in_port=%s,dl_vlan=%s,actions=mod_vlan_vid:%s,output:%s" % (oshi.name,eth_port_number,"0xffff",VLAN_IP,vi_port_number))
		oshi.cmd("ovs-ofctl add-flow br-%s hard_timeout=0,priority=300,in_port=%s,dl_vlan=%s,actions=strip_vlan,output:%s" % (oshi.name,vi_port_number,VLAN_IP,eth_port_number)) 
			
def conf_flows_vlan_approach(oshi, eth_ports, vi_ports):
	print "*** Configuring Flows Classifier A For", oshi
	VLAN_IP = 1
	size = len(eth_ports)
	i = 0
	for i in range(size):
		oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " hard_timeout=0,priority=300,in_port=" + str(eth_ports[i])
		+ ",dl_vlan=" + str(VLAN_IP) + ",action=output:" + str(vi_ports[i]))
		oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " hard_timeout=0,priority=300,in_port=" + str(vi_ports[i])
		+ ",dl_vlan=" + str(VLAN_IP) + ",action=output:" + str(eth_ports[i]))
	oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " hard_timeout=0,priority=400,dl_type=0x88cc,action=controller")
	oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " hard_timeout=0,priority=400,dl_type=0x8942,action=controller")

def conf_flow_no_vlan_approach(oshi, eth_ports, vi_ports):
	print "*** Configuring Flows Classifier B For", oshi	
	size = len(eth_ports)
	i = 0
	oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " \"table=0,hard_timeout=0,priority=300,dl_vlan=0xffff,actions=resubmit(,1)\"")
	for i in range(size):
		oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " \"table=1,hard_timeout=0,priority=300,in_port=" + str(eth_ports[i])
		+ ",action=output:" + str(vi_ports[i]) + "\"")
		oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " \"table=1,hard_timeout=0,priority=300,in_port=" + str(vi_ports[i])
		+ ",action=output:" + str(eth_ports[i]) + "\"")
	oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " \"table=1,hard_timeout=0,priority=400,dl_type=0x88cc,action=controller\"")
	oshi.cmd("ovs-ofctl add-flow br-" + oshi.name + " \"table=1,hard_timeout=0,priority=400,dl_type=0x8942,action=controller\"")

def clean_env(oshi):
	print "*** Cleaning Environment For", oshi.name
	shutil.rmtree("/tmp/" + oshi.name, ignore_errors=True)

def configure_quagga(oshi):
	print "*** Configuring Quagga For", oshi.name
	path_quagga = "/tmp/" + oshi.name + "/quagga"
	os.mkdir(path_quagga)
	zebra_conf = open(path_quagga + "/zebra.conf","w")
	ospfd_conf = open(path_quagga + "/ospfd.conf","w")
	ospfd_nets = []
	ospfd_conf.write("hostname %s\n" % oshi.name)
	ospfd_conf.write("password zebra\n")
	ospfd_conf.write("log file /var/log/quagga/ospfd.log\n\n")
	zebra_conf.write("hostname %s\n" % oshi.name)
	zebra_conf.write("password zebra\n")
	zebra_conf.write("enable password zebra\n")
	zebra_conf.write("log file /var/log/quagga/zebra.log\n\n")
	for net in nets:
		intfs_to_conf = net.belong(oshi.name)
		if(len(intfs_to_conf) > 0):
			ospfd_nets.append(("%s.%s.%s.%s" %(net.subnet[0], net.subnet[1], net.subnet[2], 0), ip_netbit,(net.area)))
			for intf_to_conf in intfs_to_conf:
				ip = net.give_me_next_ip()
				if CORE_APPROACH == "A":
					intfname = configure_ospf_vlan_approach(oshi, intf_to_conf)
				elif CORE_APPROACH == "B":
					intfname = configure_ospf_no_vlan_approach(oshi, intf_to_conf)
				ospfd_conf.write("interface " + intfname + "\n")
				ospfd_conf.write("ospf cost %s\n" % net.cost)
				ospfd_conf.write("ospf hello-interval %s\n\n" % net.hello_int)
				zebra_conf.write("interface " + intfname + "\n")
				zebra_conf.write("ip address %s/%s\n" %(ip, ip_netbit))
				zebra_conf.write("link-detect\n\n")
	intfname = 'lo'
	if type(oshi) is RemoteController:
		ip = give_me_next_loopback()
	else:
		ip = oshi.loopback
	ospfd_conf.write("interface " + intfname + "\n")
	ospfd_conf.write("ospf cost %s\n" % 1)
	ospfd_conf.write("ospf hello-interval %s\n\n" % 2)
	zebra_conf.write("interface " + intfname + "\n")
	zebra_conf.write("ip address %s/%s\n" %(ip, 32))
	zebra_conf.write("link-detect\n\n")
	ospfd_conf.write("router ospf\n")
	ospfd_nets.append((ip, 32, "0.0.0.0"))
	for ospfd_net in ospfd_nets:	
		ospfd_conf.write("network %s/%s area %s\n" %(ospfd_net[0], ospfd_net[1] , ospfd_net[2]))
	ospfd_conf.close()
	zebra_conf.close()
	oshi.cmd("chmod -R 777 /var/log/quagga")
	oshi.cmd("chmod -R 777 /var/run/quagga")	
	oshi.cmd("chmod -R 777 %s" %(path_quagga))

def configure_ospf_vlan_approach(oshi, intfname):
	VLAN_IP = 1
	if 'c1' not in oshi.name:
		intfname = "vi%s" % (strip_number(intfname))
	oshi.cmd('ip link set %s up' % intfname)
	oshi.cmd('modprobe 8021q')
	oshi.cmd('vconfig add %s %s' % (intfname, VLAN_IP))
	intfname = intfname + "." + str(VLAN_IP)
	return intfname

def configure_ospf_no_vlan_approach(oshi, intfname):
	if 'c1' not in oshi.name:
		intfname = "vi%s" % (strip_number(intfname))
	oshi.cmd('ip link set %s up' % intfname)
	return intfname

def configure_vll_pusher(net):
	print "*** Create Configuration File For Vll Pusher"
	path = vll_path + "vll_pusher.cfg"
	vll_pusher_cfg = open(path,"w")
	for i in range(0, len(LHS_tunnel_aoshi)):
		aoshi = LHS_tunnel_aoshi[i]		
		lhs_dpid = net.getNodeByName(aoshi).dpid
		lhs_dpid = ':'.join(s.encode('hex') for s in lhs_dpid.decode('hex'))
		port = LHS_tunnel_port[i]
		lhs_port = port
		aoshi = RHS_tunnel_aoshi[i]		
		rhs_dpid = net.getNodeByName(aoshi).dpid
		rhs_dpid = ':'.join(s.encode('hex') for s in rhs_dpid.decode('hex'))
		port = RHS_tunnel_port[i]
		rhs_port = port
		vll_pusher_cfg.write("%s|%s|%s|%s|%d|%d|\n" % (lhs_dpid, rhs_dpid, lhs_port, rhs_port, LHS_tunnel_vlan[i], RHS_tunnel_vlan[i]))
	vll_pusher_cfg.close()
	root = Node( 'root', inNamespace=False )
	root.cmd("chmod 777 %s" %(path))
	
def init_net(net):
	"Init Function"
	root = Node( 'root', inNamespace=False )
	root.cmd('stop avahi-daemon')
	root.cmd('killall dhclient')
	root.cmd('killall zebra')
	root.cmd('killall ospfd')
	fixEnvironment()
	print "*** Restarting Network Manager"
	time.sleep(10)
	root.cmd('service network-manager restart')
	time.sleep(2)	
	net.start()

	# Configure the ctrl
	for ctrl in ctrls:
		configure_env_ctrl(ctrl)
	for oshi in oshis:
		configure_env_oshi(oshi)
	for oshi in oshis:
		strip_ip(oshi)
		path_quagga_conf = "/tmp/" + oshi.name + "/quagga"
		oshi.cmd("%szebra -f %s/zebra.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
		oshi.cmd("%sospfd -f %s/ospfd.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
	for aoshi in aoshis:
		configure_env_oshi(aoshi)
	for aoshi in aoshis:
		strip_ip(aoshi)
		path_quagga_conf = "/tmp/" + aoshi.name + "/quagga"
		aoshi.cmd("%szebra -f %s/zebra.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
		aoshi.cmd("%sospfd -f %s/ospfd.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
	for ctrl in ctrls:	
		path_quagga_conf = "/tmp/" + ctrl.name + "/quagga"
		ctrl.cmd("%szebra -f %s/zebra.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
		ctrl.cmd("%sospfd -f %s/ospfd.conf -A 127.0.0.1 &" %(path_quagga_exec, path_quagga_conf))
	print "*** Configuring Hosts"
	i = 0
	for i in range(len(hosts)):
		host = net.getNodeByName(hosts[i])
		configure_node(host)
	configure_standalone_sw(switches)
	configure_l2_accessnetwork()
	# Configure VLL Pusher
	configure_vll_pusher(net)
	print "*** Type 'exit' or control-D to shut down network"
	CLI( net )
	net.stop()
	subprocess.call(["sudo", "mn", "-c"], stdout=None, stderr=None)
	for oshi in oshis:
		clean_env(oshi)	
	for aoshi in aoshis:
		clean_env(aoshi)	
	for ctrl in ctrls:
		clean_env(ctrl)
	path = vll_path + "vlls.json"
	if(os.path.exists(path)):
		print "*** Remove Vlls DB File"
		os.remove(path)
	print '*** Unmounting host bind mounts'
	root.cmd('service network-manager restart')
	root.cmd('start avahi-daemon') 
	root.cmd('killall ovsdb-server')
	root.cmd('killall ovs-vswitchd')
	root.cmd('killall zebra')
	root.cmd('killall ospfd')
	root.cmd('/etc/init.d/openvswitch-switch restart') 
	unmountAll()

def parse_cmd_line():
	parser = argparse.ArgumentParser(description='Mininet Deployer')
	parser.add_argument('--topology', dest='topoInfo', action='store', default='mesh:3', help='Topology Info topo:param, e.g., mesh:3 or file:topo.json')
	args = parser.parse_args()	
	if len(sys.argv)==1:
    		parser.print_help()
    		sys.exit(1)
	data = args.topoInfo.split(":")	
	return (data[0], data[1])

def check_precond():
	unmountAll()
	if vll_path == "" or path_quagga_exec == "":
		print "Error Set Environment Variable At The Beginning Of File"
		sys.exit(-2)


if __name__ == '__main__':
	
	net = None
	lg.setLogLevel('info')
	(topo, param) = parse_cmd_line()
	check_precond()
	if topo == 'file':
		print "*** Create Topology From File:", param
		net = buildTopoFromFile(param)
	elif topo == 'mesh':
		print "*** Create Built-in Topology mesh[%s]" % param
		net = Mesh(int(param))
	else:
		print "*** Create Topology From Networkx:", topo, param
		net = buildTopoFromNx(topo,param)
	init_net(net)
