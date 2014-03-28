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
# Deployer Utils.
#
# @author Pier Luigi Ventre <pl.ventre@gmail.com>
# @author Giuseppe Siracusano <a_siracusano@tin.it>
# @author Stefano Salsano <stefano.salsano@uniroma2.it>
#
#

from os.path import realpath
from mininet.util import errFail, quietRun, errRun
from mininet.log import debug, info

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




