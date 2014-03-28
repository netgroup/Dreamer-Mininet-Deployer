Dreamer-Mininet-Deployer
========================

Mininet Deployer For Dreamer Project (GÉANT Open Call)

Set Environment Variable At The Beginning of mininet_deployer.py

usage: mininet_deployer.py [-h] [--topology TOPOINFO]

Mininet Deployer

Dependecies For The Usage Of Networkx
	1) networkx + its dependecies
	2) pygraphviz
	3) matplotlib

When you use networkx the topo's png is saved in topo.png

optional arguments:
  -h, --help           show this help message and exit
  --topology TOPOINFO  Topology Info topo:param
	1)In order to use the built-in topology mesh[x] -> mesh:3
	2)In order to use the topology topo.json in /topo/ -> file:topo.json
	3)In order to use random generation of networkx e-r:n,p (i.e number of core nodes, interconnection probability)
