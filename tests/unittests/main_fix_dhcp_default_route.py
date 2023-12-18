#!/usr/bin/python3

import sys
from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings

print("PATH = {}".format(sys.path))

#sys.path.insert(0,'/gsa/ausgsa/home/s/t/sttran/PROJECTS/CLOUD-INIT/WORKSPACE')

print("PATH = {}".format(sys.path))

#from cloudinit.distros import aix

hostname_conf_fn = "/tmp/hosts"
resolve_conf_fn = "/tmp/resolv.conf"


BASE_NET_CFG = '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 9.3.148.132
    netmask 255.255.254.0
    broadcast 9.3.255.255
    gateway 9.3.149.1
    dns-nameservers 9.3.1.200 9.0.128.50
    dns-search aus.stglabs.ibm.com

auto eth1
iface eth1 inet dhcp
    dns-search aus.stglabs.ibm.com
'''


#
# MAIN EXECUTION HERE
#
# True for bring_up
#
cls = distros.fetch('aix')
cfg = settings.CFG_BUILTIN
cfg['system_info']['distro'] = 'aix'
paths = helpers.Paths({})
aix = cls('aix', cfg, paths)

aix.apply_network(BASE_NET_CFG, True)
