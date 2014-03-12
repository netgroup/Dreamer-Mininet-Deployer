#!/usr/bin/python

from mininet.net import Mininet
import time
from mininet.cli import CLI
from mininet.node import RemoteController, Host, Node, OVSKernelSwitch
from mininet.link import Link
from mininet.util import errFail, quietRun, errRun
from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel, info, debug
from mininet.log import lg

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt

from os.path import realpath
from functools import partial
import subprocess
import os
import shutil
import sys
import re
import argparse

# This code has been taken from mininet's example bind.py, but we had to fix some stuff
# because some thing don't work properly, for example xterm. We add when necessary explanation
# of the code

# Utility functions for unmounting a tree

# Real path of OSHI's dir
MNRUNDIR = realpath( '/var/run/mn' )

# Take the mounted points of the root machine
def mountPoints():
    "Return list of mounted file systems"
    mtab, _err, _ret = errFail( 'cat /proc/mounts' )
    lines = mtab.split( '\n' )
    mounts = []
    for line in lines:
        if not line:
            continue
        fields = line.split( ' ')
        mount = fields[ 1 ]
        mounts.append( mount )
    return mounts

# Utility Function for unmount all the dirs
def unmountAll( rootdir=MNRUNDIR ):
    "Unmount all mounts under a directory tree"
    rootdir = realpath( rootdir )
    # Find all mounts below rootdir
    # This is subtle because /foo is not
    # a parent of /foot
    dirslash = rootdir + '/'
    mounts = [ m for m in mountPoints()
              if m == dir or m.find( dirslash ) == 0 ]
    # Unmount them from bottom to top
    mounts.sort( reverse=True )
    for mount in mounts:
        debug( 'Unmounting', mount, '\n' )
        _out, err, code = errRun( 'umount', mount )
        if code != 0:
            info( '*** Warning: failed to umount', mount, '\n' )
            info( err )

# Class that inherits from Host and extends it with the funcion
# of the private dir
class HostWithPrivateDirs( Host ):
    "Host with private directories"

    mnRunDir = MNRUNDIR
    dpidLen = 16

    def __init__(self, name, dpid=None, *args, **kwargs ):
        """privateDirs: list of private directories
           remounts: dirs to remount
           unmount: unmount dirs in cleanup? (True)
           Note: if unmount is False, you must call unmountAll()
           manually."""
        self.privateDirs = kwargs.pop( 'privateDirs', [] )
        self.remounts = kwargs.pop( 'remounts', [] )
        self.unmount = kwargs.pop( 'unmount', True )
        Host.__init__( self, name, *args, **kwargs )
        self.rundir = '%s/%s' % ( self.mnRunDir, name )
        self.root, self.private = None, None  # set in createBindMounts
        if self.privateDirs:
            self.privateDirs = [ realpath( d ) for d in self.privateDirs ]
            self.createBindMounts()
        # These should run in the namespace before we chroot,
        # in order to put the right entries in /etc/mtab
        # Eventually this will allow a local pid space
        # Now we chroot and cd to wherever we were before.
        pwd = self.cmd( 'pwd' ).strip()
        self.sendCmd( 'exec chroot', self.root, 'bash -ms mininet:'
                       + self.name )
        self.waiting = False
        self.cmd( 'cd', pwd )
        # In order for many utilities to work,
        # we need to remount /proc and /sys
        self.cmd( 'mount /proc' )
        self.cmd( 'mount /sys' )
	self.dpid = dpid if dpid else self.defaultDpid()
    
    def defaultDpid( self ):
        "Derive dpid from switch name, s1 -> 1"
        try:
            dpid = int( re.findall( r'\d+', self.name )[ 0 ] )
            dpid = hex( dpid )[ 2: ]
            dpid = '0' * ( self.dpidLen - len( dpid ) ) + dpid
            return dpid
        except IndexError:
            raise Exception( 'Unable to derive default datapath ID - '
                             'please either specify a dpid or use a '
                             'canonical switch name such as s23.' )

    def mountPrivateDirs( self ):
        "Create and bind mount private dirs"
        for dir_ in self.privateDirs:
            privateDir = self.private + dir_
            errFail( 'mkdir -p ' + privateDir )
            mountPoint = self.root + dir_
	    #print mountPoint
            errFail( 'mount -B %s %s' %
                           ( privateDir, mountPoint) )

    def mountDirs( self, dirs ):
        "Mount a list of directories"
        for dir_ in dirs:
            mountpoint = self.root + dir_
	    #print mountpoint
            errFail( 'mount -B %s %s' %
                     ( dir_, mountpoint ) )

    @classmethod
    def findRemounts( cls, fstypes=None ):
        """Identify mount points in /proc/mounts to remount
           fstypes: file system types to match"""
        if fstypes is None:
            fstypes = [ 'nfs' ]
        dirs = quietRun( 'cat /proc/mounts' ).strip().split( '\n' )
        remounts = []
        for dir_ in dirs:
            line = dir_.split()
            mountpoint, fstype = line[ 1 ], line[ 2 ]
            # Don't re-remount directories!!!
            if mountpoint.find( cls.mnRunDir ) == 0:
                continue
            if fstype in fstypes:
                remounts.append( mountpoint )
        return remounts

    def createBindMounts( self ):
        """Create a chroot directory structure,
           with self.privateDirs as private dirs"""
        errFail( 'mkdir -p '+ self.rundir )
        unmountAll( self.rundir )
        # Create /root and /private directories
        self.root = self.rundir + '/root'
        self.private = self.rundir + '/private'
        errFail( 'mkdir -p ' + self.root )
        errFail( 'mkdir -p ' + self.private )
        # Recursively mount / in private doort
        # note we'll remount /sys and /proc later
        errFail( 'mount -B / ' + self.root )
        self.mountDirs( self.remounts )
        self.mountPrivateDirs()

    def unmountBindMounts( self ):
        "Unmount all of our bind mounts"
        unmountAll( self.rundir )

    def popen( self, *args, **kwargs ):
        "Popen with chroot support"
        chroot = kwargs.pop( 'chroot', True )
        mncmd = kwargs.get( 'mncmd',
                           [ 'mnexec', '-a', str( self.pid ) ] )
        if chroot:
            mncmd = [ 'chroot', self.root ] + mncmd
            kwargs[ 'mncmd' ] = mncmd
        return Host.popen( self, *args, **kwargs )

    def cleanup( self ):
        """Clean up, then unmount bind mounts
           unmount: actually unmount bind mounts?"""
        # Wait for process to actually terminate
        self.shell.wait()
        Host.cleanup( self )
        if self.unmount:
            self.unmountBindMounts()
            errFail( 'rmdir ' + self.root )

# Convenience aliases

findRemounts = HostWithPrivateDirs.findRemounts

def fixIntf(hosts):
	for i in range(0, len(hosts)):
		for obj in hosts[i].nameToIntf:
	  		if 'lo' not in obj:
				fixNetworkManager(obj)	
		fixNetworkManager(hosts[i])    
	

def fixNetworkManager(intf):
	cfile = '/etc/network/interfaces'
  	line1 = 'iface %s inet manual\n' % intf
  	config = open( cfile ).read()
  	if ( line1 ) not in config:
		print '*** Adding', line1.strip(), 'to', cfile
		with open( cfile, 'a' ) as f:
	  		f.write( line1 )
	  	f.close();

def fixEnvironment():
	cfile = '/etc/environment'
  	line1 = 'VTYSH_PAGER=more\n'
  	config = open( cfile ).read()
  	if ( line1 ) not in config:
		print '*** Adding', line1.strip(), 'to', cfile
		with open( cfile, 'a' ) as f:
	  		f.write( line1 )
	  	f.close();

aoshis = []
oshis = []
nets = []
switches = []
L2nets = []

# XXX Parameter 

# Vll path
vll_path = "../sdn_controller_app/vll_pusher_for_floodlights/"
# Executable path
path_quagga_exec = "/usr/lib/quagga/"
# IP Parameter
subnet = "192.168."
netbit = 24
# We start from 1 because in 192.168.0.0 we have the controller
lastnet = 1

# Controller Parameter
ctrls_ip = ['192.168.0.1']
ctrls_port = [6633]

# For now unused, they are the l2 ovs controller's parameter
# ctrl_root_ip = '127.0.0.1'
# ctrl_root_port = 6633

# Round Robin index. It will used to split up the OSHI load
next_ctrl = 0

# Set of Controller
ctrls = []
# Set of Hosts
hosts = []


sdn_subnet = "10.0."
sdn_netbit = 24
sdn_lastnet = 0
last_sdn_host = 1

loopback = [10, 0, None, 0]


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

# Parameter Core Approach
CORE_APPROACH = 'A' # It can be A or B

# XXX Virtual Leased Line Configuration
LHS_tunnel = ['euh1']#,'euh1','euh4','euh6']
RHS_tunnel = ['euh2']#,'euh3','euh6','euh5']
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


class L2AccessNetwork:

	def __init__(self, classification):
		self.name = "L2AccessNetwork" + str(len(L2nets) + 1);
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
	  
def configure_node(node):
	global last_sdn_host
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
					gw_ip = (net.subnet + "%s") % 1
					intf = intf_to_conf
					node.cmd('ip addr add %s/%s brd + dev %s' %(ip, netbit, intf))
					node.cmd('ip link set %s up' % intf)
					node.cmd('route add default gw %s %s' %(gw_ip, intf))
				else:
					ip = tunnel.give_me_next_ip()
					intf = intf_to_conf
					node.cmd('ip addr add %s/%s brd + dev %s' %(ip, sdn_netbit, intf))
					node.cmd('ip link set %s up' % intf)
				
def check_host():
	for i in range(0,len(LHS_tunnel)):
		host1 = LHS_tunnel[i]
		host2 = RHS_tunnel[i]
		if host1 not in hosts or host2 not in hosts:
			print "Error Misconfiguration Virtual Leased Line"
			print "Error Cannot Connect", host1, "To", host2
			sys.exit(2)
			
	
def Mesh(OSHI=4):
	global ctrls
	global oshis
	global aoshis
	global SDN_PORTS
	global TUNNEL_SETUP
	"Create A Mesh Topo"
	print "*** Mesh With", OSHI, "OSHI"
	"Creating OSHI"
	remounts = findRemounts( fstypes=[ 'devpts' ] )
	privateDirs = [ '/var/log/', '/var/log/quagga', '/var/run', '/var/run/quagga', '/var/run/openvswitch']
	host = partial( HostWithPrivateDirs, remounts=remounts,
                privateDirs=privateDirs, unmount=False )
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=host, build=False )
	i = 0
	h = 0
	print "*** Create Core Networks"
	for i in range(OSHI):
		oshi = (net.addHost('osh%s' % (i+1)))
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
	check_host()
	
	for i in range(0, len(LHS_tunnel)):
		tunnels.append(Tunnel())

	loopback[2]=sdn_lastnet

	print "*** Loopback Address Start From:", loopback 
	print "*** Tunnels LHS:", LHS_tunnel
	print "*** Tunnels RHS:", RHS_tunnel

	# Tunnels Setup
	IP_tunnel_setup()
	SDN_tunnel_setup(net)

	i = 0
	for tunnel in tunnels :	
		print "*** Tunnel %d, Subnet %s0, Intfs %s" % (i, tunnel.subnet, tunnel.intfs)
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
		print "*** OSPF Network:", network.subnet + "0,", str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int
	return net

def balanced_tree_from_nx(fanout, depth):
	g = nx.balanced_tree(fanout, depth)
	global ctrls
	"Create An Erdos Reny Topo"
	"Creating OSHI"
	remounts = findRemounts( fstypes=[ 'devpts' ] )
	privateDirs = [ '/var/log/', '/var/log/quagga', '/var/run', '/var/run/quagga', '/var/run/openvswitch']
	host = partial( HostWithPrivateDirs, remounts=remounts,
	privateDirs=privateDirs, unmount=False )
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=host, build=False )
	i = 0
	h = 0
	# This is the basic behavior, but we have to modify it in order to creare switched networks
	for n in g.nodes():
		n = n + 1
		oshi = (net.addHost('osh%s' % (n)))
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

	for network in nets:
		print "*** Create Network:", network.subnet + "0,", str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int

	pos = nx.graphviz_layout(g, prog='dot')
        nx.draw(g, pos)
        plt.savefig("topo.png")

	return net

def erdos_renyi_from_nx(n, p):
	g = nx.erdos_renyi_graph(n,p)
	global ctrls
	"Create An Erdos Reny Topo"
	"Creating OSHI"
	remounts = findRemounts( fstypes=[ 'devpts' ] )
	privateDirs = [ '/var/log/', '/var/log/quagga', '/var/run', '/var/run/quagga', '/var/run/openvswitch']
	host = partial( HostWithPrivateDirs, remounts=remounts,
	privateDirs=privateDirs, unmount=False )
	net = Mininet( controller=RemoteController, switch=OVSKernelSwitch, host=host, build=False )
	i = 0
	h = 0
	# This is the basic behavior, but we have to modify it in order to creare switched networks
	for n in g.nodes():
		n = n + 1
		oshi = (net.addHost('osh%s' % (n)))
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

	for network in nets:
		print "*** Create Network:", network.subnet + "0,", str(network.intfs) + ",", "cost %s," % network.cost, "hello interval %s," % network.hello_int

	# We generate the topo's png
	pos = nx.circular_layout(g)
        nx.draw(g, pos)
        plt.savefig("topo.png")

	return net

def topo_from_nx(topo, args):
	if topo == 'bt':
		if len(args) > 2:
			if args [0] > 10 or args[1] > 10:
				print "Warning Parameter Too High For Balanced Tree", "Fanout %s" % args[0], "Depth %s" % args[1]
				print "Using Default Parameter"
				args[0] = 2
				args[1] = 2
		else :
			args[0] = 2
			args[1] = 2	 
		print "Balanced Tree", "Fanout %s" % args[0], "Depth %s" % args[1]
		return balanced_tree_from_nx(args[0], args[1])
	
	elif topo == 'er':
		if len(args) >= 2:
			if args [0] > 10 or args[1] > 1:
				print "Warning Parameter Too High For Erdos Renyi", "Nodes %s" % args[0], "Interconnection Probability %s" % args[1]
				print "Using Default Parameter"
				args[0] = 5
				args[1] = 0.8
		else :
			args[0] = 5
			args[1] = 0.8
		print "Erdos Renyi", "Nodes %s " % args[0], "Interconnection Probability %s" % args[1]
		return erdos_renyi_from_nx(args[0], args[1])

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
		# Special Case Local Tunnel - i.e. in the same l2 net
		if side == 'RHS' and aoshi[0] == LHS_tunnel_aoshi[k]:
			value = LHS_tunnel_vlan[k]
			tag = value
		else: 
			default = 2
			value = AOSHI_TO_TAG.get(aoshi[1], default)
			tag = value
			AOSHI_TO_TAG[aoshi[1]] = value + 1
		print "*** VLAN Tag", tag
		while done == False:
			nextNode = L2nets[i].getNextHop(currentNode)
			if 'euh' in currentNode and 'sw' in nextNode[0]:
				lhs_new_link = net.getNodeByName(nextNode[0])				
				rhs_new_link = net.getNodeByName(currentNode)
				l = net.addLink(lhs_new_link, rhs_new_link)
				tunnels[k].add_intf(l.intf2.name)
				# l.intf1 contains the NextHop's new port
				ACCESS_TO_TAG[l.intf1.name] = str(tag) + ","
				z = 0
				for network in nets:
					if len(network.belong(currentNode)) > 0:
						break
					z  = z + 1
				if z == len(nets):
					print "Configuration Error"
					print "Cannot Find The Host", currentNode, "In The OSPF Networks"
					sys.exit(-2)
				network.append_intf(l.intf2.name)
				currentNode = nextNode[0]
			elif 'sw' in currentNode:
				# NextNode[2] contains the currentNode's port
				default = ""
				tags = (TRUNK_TO_TAG.get(nextNode[2], default)).split(',')
				if str(tag) not in tags:
					TRUNK_TO_TAG[nextNode[2]] = TRUNK_TO_TAG.get(nextNode[2], default) + str(tag) + ","
				if 'aos' in nextNode[0]:
					aoshi = net.getNodeByName(nextNode[0])
					if side == 'LHS':
						LHS_tunnel_aoshi.append(aoshi.name)
						LHS_tunnel_port.append(nextNode[1])
						LHS_tunnel_vlan.append(tag)
					else:
						RHS_tunnel_aoshi.append(aoshi.name)
						RHS_tunnel_port.append(nextNode[1])
						RHS_tunnel_vlan.append(tag)
					done = True
				elif 'sw' in nextNode[0]:
					# NextNode[1] contains the nextHop's port
					tags = (TRUNK_TO_TAG.get(nextNode[1], default)).split(',')
					if str(tag) not in tags:
						TRUNK_TO_TAG[nextNode[1]] = TRUNK_TO_TAG.get(nextNode[1], default) + str(tag) + ","
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
				ACCESS_TO_TAG[nextNode[1]] = tag + ","
				currentNode = nextNode[0]
			elif 'sw' in currentNode:
				# NextNode[1] contains the Link's LHS
				default = ""
				tags = (TRUNK_TO_TAG.get(nextNode[2], default)).split(',')
				if tag not in tags:
					TRUNK_TO_TAG[nextNode[2]] = TRUNK_TO_TAG.get(nextNode[2], default) + tag + ","
				if 'aos' in nextNode[0]:
					done = True
				elif 'sw' in nextNode[0]:
					tags = (TRUNK_TO_TAG.get(nextNode[1], default)).split(',')
					if tag not in tags:
						TRUNK_TO_TAG[nextNode[1]] = TRUNK_TO_TAG.get(nextNode[1], default) + tag + ","
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
		aoshi = (net.addHost('aos%s' % (i+1)))
		l = net.addLink(aoshi, oshis[i % OSHI])
		nets.append(OSPFNetwork(intfs=[l.intf1.name,l.intf2.name], ctrl=False))
		print "*** Connect", aoshi, "To", oshis[i % OSHI]
		create_l2_access_network(aoshi, net)   
		aoshis.append(aoshi)

def create_l2_access_network(aoshi, net, n_host=1):
	global switches
	global hosts
	global L2nets
	l2net = L2AccessNetwork(classification = 'B')
	print "*** Create L2 Access Network For", aoshi.name
	intfs = []
	hosts_in_rn = []
	print "*** Create L2 Switch"
	next = len(switches)
	sw = net.addSwitch("sw%s" % (next+1))
	print "*** Create Switch", sw.name
	hosts_in_rn.append(sw)
	l = net.addLink(aoshi, sw)
	print "*** Connect", aoshi, "To", sw
	l2net.addLink(l)
	intfs.append(l.intf1.name)
	switches.append(sw)

	# Create Another L2 Switch
	# temp = sw
	# next = len(switches)
	# print "*** Create Switch", sw.name
	# sw = net.addSwitch("sw%s" % (next+1))
	# hosts_in_rn.append(sw)
	# l = net.addLink(temp, sw)
	# print "*** Connect", temp, "To", sw
	# l2net.addLink(l)
	# switches.append(sw)

	print "*** Create End User Hosts"
	for i in range(len(hosts), (len(hosts) + n_host)):
		host = net.addHost(('euh%s') % (i+1))
		l = net.addLink(sw, host)
		l2net.addLink(l)
		print "*** Connect", host, "To", sw
		hosts.append(host.name)
		intfs.append(l.intf2.name)
	nets.append(OSPFNetwork(intfs, ctrl=False, hello_int=2))
	fixIntf(hosts_in_rn)
	L2nets.append(l2net)	

def strip_number(intf):
	intf = str(intf)
	a = intf.split('-')
	if len(a) > 2:
		print "*** WARNING BAD NAME FOR INTF - EXIT"
		sys.exit(-1)
	return int(a[1][3:])

def strip_ip(oshi):
	for intf in oshi.nameToIntf:
		if 'lo' not in intf:
			if 'eth0' in intf:
				oshi.cmd("ifconfig " + intf + " 0")	

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
		eth_port_number = convert_port_name_to_number(oshi.name, eth_intf)
		vi_intf = "vi%s" % strip_number(eth_intf)
		vi_port_number = convert_port_name_to_number(oshi.name, vi_intf)
		oshi.cmd("ovs-ofctl add-flow br-%s \"table=0,hard_timeout=0,priority=300,in_port=%s,dl_vlan=%s,actions=strip_vlan,resubmit(,1)\"" % (oshi.name, eth_port_number,VLAN_IP))
		oshi.cmd("ovs-ofctl add-flow br-%s \"table=1,hard_timeout=0,priority=300,in_port=%s,actions=mod_vlan_vid:%s,output:%s\"" % (oshi.name,vi_port_number,VLAN_IP,eth_port_number))

def conf_flows_ingress_egress_no_vlan_approach(oshi, i, intf):
	if CORE_APPROACH == 'B':
		print "*** Already Done Same Approach Between Core And Access"
	elif CORE_APPROACH == 'A':
		print "*** Add Rule For No Vlan Access Approach"
		VLAN_IP = 1 # Core Vlan	
		eth_intf = intf
		eth_port_number = convert_port_name_to_number(oshi.name, eth_intf)
		vi_intf = "vi%s" % strip_number(eth_intf)
		vi_port_number = convert_port_name_to_number(oshi.name, vi_intf)
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
			ospfd_nets.append(((net.subnet + "0"),netbit,(net.area)))
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
				zebra_conf.write("ip address %s/%s\n" %(ip, netbit))
				zebra_conf.write("link-detect\n\n")
	intfname = 'lo'
	ip = give_me_next_loopback()
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

def configure_standalone_sw():
	print "*** Configuring L2 Switches"
	root = Node( 'root', inNamespace=False )
	for sw in switches:
		print "*** Configuring", sw.name, "As Learning Switch"
		root.cmd("ovs-vsctl set-fail-mode %s standalone" % sw.name)
		#root.cmdPrint("ovs-ofctl add-flow %s hard_timeout=0,priority=300,action=all" % sw.name)

def convert_port_name_to_number(name, port):
	Node = net.getNodeByName(name)
	p = Node.cmd("ovs-ofctl dump-ports-desc br-%s | grep %s |awk -F '(' '{print $1}'| cut -d ' ' -f 2" %(name, port ))
	return str(int(p))

def configure_vll_pusher():
	print "*** Create Configuration File For Vll Pusher"
	path = vll_path + "vll_pusher.cfg"
	vll_pusher_cfg = open(path,"w")
	for i in range(0, len(LHS_tunnel_aoshi)):
		aoshi = LHS_tunnel_aoshi[i]
		port = LHS_tunnel_port[i]
		lhs_port = convert_port_name_to_number(aoshi, port)
		aoshi = RHS_tunnel_aoshi[i]
		port = RHS_tunnel_port[i]
		rhs_port = convert_port_name_to_number(aoshi, port)
		vll_pusher_cfg.write("%s|%s|%s|%s|%d|%d|\n" % (LHS_tunnel_aoshi[i], RHS_tunnel_aoshi[i], lhs_port, rhs_port, LHS_tunnel_vlan[i], RHS_tunnel_vlan[i]))
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
	configure_standalone_sw()
	configure_l2_accessnetwork()
	# Configure VLL Pusher
	configure_vll_pusher()
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


if __name__ == '__main__':
	unmountAll()
	net = None
	lg.setLogLevel('info')
	(topo, param) = parse_cmd_line()
	if topo == 'file':
		print "*** Create Topology From File:", param
	elif topo == 'mesh':
		print "*** Create Built-in Topology mesh[%s]" % param
	else:
		print "Error Unrecognized Topology"
	#net = Mesh(3)
	#init_net(net)


	# Cemetery of Code
	#print "*** Creating End-User Hosts"
	#i = 0
	#for i in range(OSHI): 
		#temp = net.addHost(('euh%s') % (i+1))
		#l = net.addLink(temp, oshis[i])
		#nets.append(OSPFNetwork(intfs=[l.intf1.name, l.intf2.name], ctrl=False))
		#print "*** Connect", temp, "To", oshis[i]
		#hosts.append(temp)

	#intfs = []
	#print "*** Creating L2 Switch"
	#s1 = net.addSwitch("s%s" % 1)
	#s2 = net.addSwitch("s%s" % 2)
	#s3 = net.addSwitch("s%s" % 3)
	
	#hosts_in_rn.append(c1)
	#hosts_in_rn.append(c0)
	#hosts_in_rn.append(s2)	
	#hosts_in_rn.append(s1)
	#hosts_in_rn.append(s3)

	#switches.append(s1)
	#switches.append(s2)
	#switches.append(s3)
	
	#print "*** Connect s1 To s2"
	#net.addLink(s1,s2)
	#print "*** Connect s1 To s3"
	#net.addLink(s1,s3)
	#print "*** Connect s2 To s3"
	#net.addLink(s2,s3)
	#print "*** Connect", oshi.name, "To s1"
	#l = net.addLink(oshi, s1)
	#intfs.append(l.intf1.name)
	#oshi = oshis[len(oshis)-2]
	#print "*** Connect", oshi.name, "To s2"
	#l = net.addLink(oshi, s2)
	#intfs.append(l.intf1.name)
	#print "*** Connect s3 To c1"
	#l = net.addLink(s3, c1)
	#intfs.append(l.intf2.name)
	#print "*** Connect s1 To c1"
	#l = net.addLink(s1, c1)
	#intfs.append(l.intf2.name)
	#print "*** Connect s2 To c1"
	#l = net.addLink(s2, c1)
	#intfs.append(l.intf2.name)
	#nets.append(OSPFNetwork(intfs, ctrl=True, hello_int=5))

	# Node Configuration
	# node.cmd('modprobe 8021q')
	# node.cmd('vconfig add %s %s' % (intf, VLAN_SDN))
	# intftemp = intf + "." + str(VLAN_SDN)
	# node.cmd('ip addr add %s%s/%s brd + dev %s' %(sdn_subnet, last_sdn_host, sdn_netbit, intftemp))
	# node.cmd('ip link set %s up' % intftemp)
	# last_sdn_host = last_sdn_host + 1
	
	# Configuration For NO_VLAN_APPROACH				
	# node.cmd('ip addr add %s/%s brd + dev %s' %(ip, netbit, intf))
	# node.cmd('ip link set %s up' % intf)
	# node.cmd('route add default gw %s %s' %(gw_ip, intf))	

	# Configuration For VLAN_APPROACH				

	#node.cmd('modprobe 8021q')
	#node.cmd('vconfig add %s %s' % (intf, VLAN_IP))
	#intftemp = intf + "." + str(VLAN_IP)
	#node.cmd('ip addr add %s/%s brd + dev %s' %(ip, netbit, intftemp))
	#node.cmd('ip link set %s up' % intftemp)
	#node.cmd('route add default gw %s %s' %(gw_ip, intftemp))
