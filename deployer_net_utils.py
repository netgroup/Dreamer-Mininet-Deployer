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

sdn_subnet = "10.0."
sdn_netbit = 24
sdn_lastnet = 0
last_sdn_host = 1
loopback = [10, 0, None, 0]
# IP Parameter
subnet = "192.168."
netbit = 24
# We start from 1 because in 192.168.0.0 we have the controller
lastnet = 1
# Round Robin index. It will used to split up the OSHI load
next_ctrl = 0


def give_me_next_loopback():
	if loopback[2] == None:
		print "Error Loopback Is Not Ready, First Add All Tunnels"
		sys.exit(-2)
	loopback[3] = (loopback[3] + 1) % 256
	if loopback[3] == 0:
		loopback[2] = (loopback[2] + 1) % 256
		if loopback[2] == 0:
			loopback[1] = (loopback[1] + 1) % 256
	if loopback[1] == 255 and loopback[2] == 255 and loopback[3] == 255:
		print "Loopback Address Sold Out"
		sys.exit(-2)
	return "%s.%s.%s.%s" %(loopback[0],loopback[1],loopback[2],loopback[3])


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
		global lastnet
		self.intfs = intfs
		if lastnet >= 255:
			print "Error, Reached 192.168.255.0"
			sys.exit(2)
		if ctrl:
			self.subnet = "192.168.0."
			self.host = 0
		else :
			self.subnet = (subnet + "%s.") % lastnet
			lastnet = lastnet + 1
			self.host = 0
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
		self.host = self.host + 1
		if self.host >= 255:
			print "Error, Reached " + self.subnet + ".255"
			sys.exit(2)
		return self.subnet + "%s" % self.host

class Tunnel:
	def __init__(self):
		global sdn_lastnet
		if sdn_lastnet >= 255:
			print "Error, Reached 10.0.255.0"
			sys.exit(2)
		self.subnet = (sdn_subnet + "%s.") % sdn_lastnet
		sdn_lastnet = sdn_lastnet + 1
		self.intfs = []
		self.host = 0

	def add_intf(self, intf):
		if intf not in self.intfs:
			self.intfs.append(intf)

	def belong(self, name):
		if name in self.intfs:
			return name
		return None

	def give_me_next_ip(self):
		self.host = self.host + 1
		if self.host >= 255:
			print "Error, Reached " + self.subnet + ".255"
			sys.exit(2)
		return self.subnet + "%s" % self.host
