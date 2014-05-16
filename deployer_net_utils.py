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
# Net Utils.
#
# @author Pier Luigi Ventre <pl.ventre@gmail.com>
# @author Giuseppe Siracusano <a_siracusano@tin.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#
#

sdn_subnet = [10, 0, 0, 0]
sdn_netbit = 24
loopback = [172, 168, 0, 0]
# IP Parameter
ip_subnet = [192, 168, 0, 0]
ip_netbit = 24
# Round Robin index. It will used to split up the OSHI load
next_ctrl = 0


def give_me_next_loopback():
	loopback[3] = (loopback[3] + 1) % 256
	if loopback[3] == 0:
		loopback[2] = (loopback[2] + 1) % 256
		if loopback[2] == 0:
			loopback[1] = (loopback[1] + 1) % 256
	if loopback[1] == 255 and loopback[2] == 255 and loopback[3] == 255:
		print "Loopback Address Sold Out"
		sys.exit(-2)
	return "%s.%s.%s.%s" %(loopback[0],loopback[1],loopback[2],loopback[3])

def give_me_next_ospf_net():
	global ip_subnet
	ip_subnet[2] = (ip_subnet[2] + 1) % 256
	if ip_subnet[2] == 0:
		print "Ip Subnet Address Sold Out"
		sys.exit(-2)
	return [ip_subnet[0], ip_subnet[1], ip_subnet[2], ip_subnet[3]]

def give_me_next_sdn_net():
	global sdn_subnet
	sdn_subnet[2] = (sdn_subnet[2] + 1) % 256
	if sdn_subnet[2] == 0:
		sdn_subnet[1] = (sdn_subnet[1] + 1) % 256
	if sdn_subnet[1] == 255 and sdn_subnet[2] == 255:
		print "SDN Subnet Address Sold Out"
		sys.exit(-2)
	return [sdn_subnet[0], sdn_subnet[1], sdn_subnet[2], sdn_subnet[3]]


class L2AccessNetwork:

	def __init__(self, name, classification):
		self.name = name
		self.Nodes = []
		self.Links = []
		self.classification = classification
		if classification == 'A':
			self.VlanIP = '1'
		else:
			self.VlanIP = '0'
		self.intfs = []

	def addLink(self, l):
		host1 = (l.intf1.name.split('-'))[0]
		host2 = (l.intf2.name.split('-'))[0]
		if host1 not in self.Nodes:
			self.Nodes.append(host1)
		if host2 not in self.Nodes:
			self.Nodes.append(host2)
		self.Links.append((l.intf1.name,l.intf2.name))
		self.intfs.append(l.intf1.name)
		self.intfs.append(l.intf2.name)

	def belong(self, name):
		ret_intfs = []
		for intf in self.intfs:
			if name in intf:
				ret_intfs.append(intf)
		return ret_intfs

	def getNextHop(self, node):
		if node not in self.Nodes:
			return None
		if 'euh' in node:
			intfToFind = "%s-eth0" % node
			for link in self.Links:
				if intfToFind == link[0]:
					return ((link[1].split("-"))[0], link[0], link[1])
				elif intfToFind == link[1]:
					return ((link[0].split("-"))[0], link[0], link[1])
		elif 'sw' in node:
			intfToFind = "%s-eth1" % node
			for link in self.Links:
				if intfToFind == link[0]:
					return ((link[1].split("-"))[0], link[0], link[1])
				elif intfToFind == link[1]:
					return ((link[0].split("-"))[0], link[0], link[1])
		elif 'aos' in node:
			return None

	def getAoshi(self, node):
		node = self.getNextHop(node)
		while 'aos' not in node[0]:
			node = self.getNextHop(node[0])
	 	return node

class OSPFNetwork: 
	def __init__(self, intfs, ctrl, cost=1, hello_int=2, area="0.0.0.0"):
		self.intfs = intfs
		if ctrl:
			self.subnet = [192, 168, 0, 0]
		else :
			self.subnet = give_me_next_ospf_net()
		self.cost = cost
		self.hello_int = hello_int
		self.area = area
	
	def append_intf(self, intf):
		if intf in self.intfs:	
			print "Discarding Append - ", intf, "Already Added"
			return
		self.intfs.append(intf) 
		return

	def belong(self, name):
		ret_intfs = []
		for intf in self.intfs:
			if name in intf:
				ret_intfs.append(intf)
		return ret_intfs

	def give_me_next_ip(self):
		self.subnet[3] = self.subnet[3] + 1
		if self.subnet == 255:
			print "Error, Reached " + self.subnet
			sys.exit(2)
		return "%s.%s.%s.%s" % (self.subnet[0], self.subnet[1], self.subnet[2], self.subnet[3])

class Tunnel:
	def __init__(self):
		self.subnet = give_me_next_sdn_net()
		self.intfs = []

	def add_intf(self, intf):
		if intf not in self.intfs:
			self.intfs.append(intf)

	def belong(self, name):
		if name in self.intfs:
			return name
		return None

	def give_me_next_ip(self):
		self.subnet[3] = self.subnet[3] + 1
		if self.subnet == 255:
			print "Error, Reached " + self.subnet
			sys.exit(2)
		return "%s.%s.%s.%s" % (self.subnet[0], self.subnet[1], self.subnet[2], self.subnet[3])
