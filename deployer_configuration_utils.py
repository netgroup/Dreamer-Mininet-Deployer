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
# Deployer Configuration Utils.
#
# @author Pier Luigi Ventre <pl.ventre@gmail.com>
# @author Giuseppe Siracusano <a_siracusano@tin.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#
#

from mininet.node import Node

def convert_port_name_to_number(oshi, port):
	p = oshi.cmd("ovs-ofctl dump-ports-desc br-%s | grep %s |awk -F '(' '{print $1}'| cut -d ' ' -f 2" %(oshi.name, port ))
	return str(int(p))

def configure_standalone_sw(switches):
	print "*** Configuring L2 Switches"
	root = Node( 'root', inNamespace=False )
	for sw in switches:
		print "*** Configuring", sw.name, "As Learning Switch"
		root.cmd("ovs-vsctl set-fail-mode %s standalone" % sw.name)




