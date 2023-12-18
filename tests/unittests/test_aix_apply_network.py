#!/usr/bin/python3


import sys
import os

# DECLARE AFTER THIS FOR TESTING CLOUDINIT

from cloudinit.config import cc_runcmd

from cloudinit import cloud
from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings


print("PATH = {}".format(sys.path))

#from cloudinit.distros import aix


hostname_conf_fn = "/tmp/hosts"
resolve_conf_fn = "/tmp/resolv.conf"


BASE_NET_CFG = '''
auto lo
iface lo inet loopback

iface eth1 inet6 static
    address 2001::2
    hwaddres ether ca:6a:b2:42:97:02
    netmask 64
    mtu 9600
    pre-up [ $(ifconfig eth1 | grep -o -E '([[:xdigit:]]{1,2}:){5}[[:xdigit:]]{1,2}') = "ca:6a:b2:42:97:02" ]
    dns-search aus.stglabs.ibm.com
'''
#iface eth2 inet6 static
#    address 2001::20
#    netmask 64
#    gateway 2001::20



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



