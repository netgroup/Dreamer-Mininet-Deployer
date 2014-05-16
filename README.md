![Alt text](repo_data/dreamer-logo.png "Optional title")

Dreamer-Mininet-Deployer
========================

Mininet Deployer For Dreamer Project (GÉANT Open Call)

Using this tool you can deploy your topology of OSHI node and the
set of services that we support (Classification and VLL).

License
=======

This sofware is licensed under the Apache License, Version 2.0.

Information can be found here:
 [Apache License 2.0](http://www.apache.org/licenses/LICENSE-2.0).

Tips
==============

Set Environment Variable At The Beginning of mininet_deployer.py
(vll_path, quagga_exec)

When you choose the build of Topology from json file, the topology
must be saved in topo folder

When you use networkx the topo's png is saved in topo.png

Mininet Deployer Dependecies
=============================
0) mininet

1) networkx + its dependecies

2) pygraphviz

3) matplotlib

Usage
=====

sudo ./mininet_deployer.py [-h] [--topology TOPOINFO]

optional arguments:

  -h, --help           show this help message and exit

  --topology TOPOINFO  Topology Info topo:param

		1)In order to use the built-in topology mesh[x] -> mesh:3

		2)In order to use the topology topo.json in ./topo/ -> file:topo.json

		3)In order to use random generation of networkx e-r:n,p (i.e number of core nodes, interconnection probability)
