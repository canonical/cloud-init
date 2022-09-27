# This file is part of cloud-init. See LICENSE file for license information.

import re

from cloudinit.distros.parsers.ifconfig import Ifconfig
from tests.unittests.helpers import TestCase


class TestSysConfHelper(TestCase):
    def test_parse_freebsd(self):
        ifs = """
vtnet0: flags=8863<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
        options=c00b8<VLAN_MTU,VLAN_HWTAGGING,JUMBO_MTU,VLAN_HWCSUM,VLAN_HWTSO,LINKSTATE>
        ether 96:00:00:a3:2d:e0
        inet 203.0.113.41 netmask 0xffffffff broadcast 203.0.113.41
        inet6 fe80::9400:ff:fea3:2de0%vtnet0 prefixlen 64 scopeid 0x1
        media: Ethernet autoselect (10Gbase-T <full-duplex>)
        status: active
        nd6 options=21<PERFORMNUD,AUTO_LINKLOCAL>
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> metric 0 mtu 16384
        options=680003<RXCSUM,TXCSUM,LINKSTATE,RXCSUM_IPV6,TXCSUM_IPV6>
        inet6 ::1 prefixlen 128
        inet6 fe80::1%lo0 prefixlen 64 scopeid 0x2
        inet 127.0.0.1 netmask 0xff000000
        groups: lo
        nd6 options=21<PERFORMNUD,AUTO_LINKLOCAL>
bridge0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
        ether 58:9c:fc:10:eb:7d
        inet 192.168.17.1 netmask 0xffffff00 broadcast 192.168.17.255
        inet6 fe80::5a9c:fcff:fe10:eb7d%bridge0 prefixlen 64 scopeid 0x3
        inet6 2001:db8:c01:bdb0::1 prefixlen 64
        id 00:00:00:00:00:00 priority 32768 hellotime 2 fwddelay 15
        maxage 20 holdcnt 6 proto rstp maxaddr 2000 timeout 1200
        root id 00:00:00:00:00:00 priority 32768 ifcost 0 port 0
        member: epair40a flags=143<LEARNING,DISCOVER,AUTOEDGE,AUTOPTP>
                ifmaxaddr 0 port 7 priority 128 path cost 2000
        member: epair30a flags=143<LEARNING,DISCOVER,AUTOEDGE,AUTOPTP>
                ifmaxaddr 0 port 6 priority 128 path cost 2000
        member: epair20a flags=143<LEARNING,DISCOVER,AUTOEDGE,AUTOPTP>
                ifmaxaddr 0 port 5 priority 128 path cost 2000
        groups: bridge
        nd6 options=21<PERFORMNUD,AUTO_LINKLOCAL>
epair10a: flags=8963<UP,BROADCAST,RUNNING,PROMISC,SIMPLEX,MULTICAST> metric 0 mtu 1500
        description: vnet-webserver
        options=8<VLAN_MTU>
        ether 02:33:0e:52:1d:0a
        groups: epair
        media: Ethernet 10Gbase-T (10Gbase-T <full-duplex>)
        status: active
        nd6 options=29<PERFORMNUD,IFDISABLED,AUTO_LINKLOCAL>
epair20a: flags=8963<UP,BROADCAST,RUNNING,PROMISC,SIMPLEX,MULTICAST> metric 0 mtu 1500
        description: vnet-scratchpad
        options=8<VLAN_MTU>
        ether 02:8e:59:ec:9a:0a
        groups: epair
        media: Ethernet 10Gbase-T (10Gbase-T <full-duplex>)
        status: active
        nd6 options=29<PERFORMNUD,IFDISABLED,AUTO_LINKLOCAL>
epair30a: flags=8963<UP,BROADCAST,RUNNING,PROMISC,SIMPLEX,MULTICAST> metric 0 mtu 1500
        description: vnet-webirc
        options=8<VLAN_MTU>
        ether 02:b3:9b:45:fe:0a
        groups: epair
        media: Ethernet 10Gbase-T (10Gbase-T <full-duplex>)
        status: active
        nd6 options=29<PERFORMNUD,IFDISABLED,AUTO_LINKLOCAL>
        """
        ifs = Ifconfig(contents)

