# This file is part of cloud-init. See LICENSE file for license information.

import os
from six import StringIO
import stat
from textwrap import dedent

try:
    from unittest import mock
except ImportError:
    import mock
try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

from cloudinit import distros
from cloudinit.distros.parsers.sys_conf import SysConf
from cloudinit import helpers
from cloudinit.net import eni
from cloudinit import settings
from cloudinit.tests.helpers import FilesystemMockingTestCase
from cloudinit import util


BASE_NET_CFG = '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5
    broadcast 192.168.1.0
    gateway 192.168.1.254
    netmask 255.255.255.0
    network 192.168.0.0

auto eth1
iface eth1 inet dhcp
'''

BASE_NET_CFG_IPV6 = '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5
    netmask 255.255.255.0
    network 192.168.0.0
    broadcast 192.168.1.0
    gateway 192.168.1.254

iface eth0 inet6 static
    address 2607:f0d0:1002:0011::2
    netmask 64
    gateway 2607:f0d0:1002:0011::1

iface eth1 inet static
    address 192.168.1.6
    netmask 255.255.255.0
    network 192.168.0.0
    broadcast 192.168.1.0
    gateway 192.168.1.254

iface eth1 inet6 static
    address 2607:f0d0:1002:0011::3
    netmask 64
    gateway 2607:f0d0:1002:0011::1
'''

V1_NET_CFG = {'config': [{'name': 'eth0',

                          'subnets': [{'address': '192.168.1.5',
                                       'broadcast': '192.168.1.0',
                                       'gateway': '192.168.1.254',
                                       'netmask': '255.255.255.0',
                                       'type': 'static'}],
                          'type': 'physical'},
                         {'name': 'eth1',
                          'subnets': [{'control': 'auto', 'type': 'dhcp4'}],
                          'type': 'physical'}],
              'version': 1}

V1_NET_CFG_OUTPUT = """
# This file is generated from information provided by
# the datasource.  Changes to it will not persist across an instance.
# To disable cloud-init's network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5/24
    broadcast 192.168.1.0
    gateway 192.168.1.254

auto eth1
iface eth1 inet dhcp
"""

V1_NET_CFG_IPV6 = {'config': [{'name': 'eth0',
                               'subnets': [{'address':
                                            '2607:f0d0:1002:0011::2',
                                            'gateway':
                                            '2607:f0d0:1002:0011::1',
                                            'netmask': '64',
                                            'type': 'static'}],
                               'type': 'physical'},
                              {'name': 'eth1',
                               'subnets': [{'control': 'auto',
                                            'type': 'dhcp4'}],
                               'type': 'physical'}],
                   'version': 1}


V1_TO_V2_NET_CFG_OUTPUT = """
# This file is generated from information provided by
# the datasource.  Changes to it will not persist across an instance.
# To disable cloud-init's network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    version: 2
    ethernets:
        eth0:
            addresses:
            - 192.168.1.5/24
            gateway4: 192.168.1.254
        eth1:
            dhcp4: true
"""

V2_NET_CFG = {
    'ethernets': {
        'eth7': {
            'addresses': ['192.168.1.5/24'],
            'gateway4': '192.168.1.254'},
        'eth9': {
            'dhcp4': True}
    },
    'version': 2
}


V2_TO_V2_NET_CFG_OUTPUT = """
# This file is generated from information provided by
# the datasource.  Changes to it will not persist across an instance.
# To disable cloud-init's network configuration capabilities, write a file
# /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg with the following:
# network: {config: disabled}
network:
    ethernets:
        eth7:
            addresses:
            - 192.168.1.5/24
            gateway4: 192.168.1.254
        eth9:
            dhcp4: true
    version: 2
"""


class WriteBuffer(object):
    def __init__(self):
        self.buffer = StringIO()
        self.mode = None
        self.omode = None

    def write(self, text):
        self.buffer.write(text)

    def __str__(self):
        return self.buffer.getvalue()


class TestNetCfgDistro(FilesystemMockingTestCase):

    frbsd_ifout = """\
hn0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> metric 0 mtu 1500
        options=51b<RXCSUM,TXCSUM,VLAN_MTU,VLAN_HWTAGGING,TSO4,LRO>
        ether 00:15:5d:4c:73:00
        inet6 fe80::215:5dff:fe4c:7300%hn0 prefixlen 64 scopeid 0x2
        inet 10.156.76.127 netmask 0xfffffc00 broadcast 10.156.79.255
        nd6 options=23<PERFORMNUD,ACCEPT_RTADV,AUTO_LINKLOCAL>
        media: Ethernet autoselect (10Gbase-T <full-duplex>)
        status: active
"""

    def setUp(self):
        super(TestNetCfgDistro, self).setUp()
        self.add_patch('cloudinit.util.system_is_snappy', 'm_snappy')
        self.add_patch('cloudinit.util.system_info', 'm_sysinfo')
        self.m_sysinfo.return_value = {'dist': ('Distro', '99.1', 'Codename')}

    def _get_distro(self, dname, renderers=None):
        cls = distros.fetch(dname)
        cfg = settings.CFG_BUILTIN
        cfg['system_info']['distro'] = dname
        if renderers:
            cfg['system_info']['network'] = {'renderers': renderers}
        paths = helpers.Paths({})
        return cls(dname, cfg.get('system_info'), paths)

    def test_simple_write_ub(self):
        ub_distro = self._get_distro('ubuntu')
        with ExitStack() as mocks:
            write_bufs = {}

            def replace_write(filename, content, mode=0o644, omode="wb"):
                buf = WriteBuffer()
                buf.mode = mode
                buf.omode = omode
                buf.write(content)
                write_bufs[filename] = buf

            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))

            ub_distro.apply_network(BASE_NET_CFG, False)

            self.assertEqual(len(write_bufs), 1)
            eni_name = '/etc/network/interfaces.d/50-cloud-init.cfg'
            self.assertIn(eni_name, write_bufs)
            write_buf = write_bufs[eni_name]
            self.assertEqual(str(write_buf).strip(), BASE_NET_CFG.strip())
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_eni_ub(self):
        ub_distro = self._get_distro('ubuntu')
        with ExitStack() as mocks:
            write_bufs = {}

            def replace_write(filename, content, mode=0o644, omode="wb"):
                buf = WriteBuffer()
                buf.mode = mode
                buf.omode = omode
                buf.write(content)
                write_bufs[filename] = buf

            # eni availability checks
            mocks.enter_context(
                mock.patch.object(util, 'which', return_value=True))
            mocks.enter_context(
                mock.patch.object(eni, 'available', return_value=True))
            mocks.enter_context(
                mock.patch.object(util, 'ensure_dir'))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))
            mocks.enter_context(
                mock.patch("cloudinit.net.eni.glob.glob",
                           return_value=[]))

            ub_distro.apply_network_config(V1_NET_CFG, False)

            self.assertEqual(len(write_bufs), 2)
            eni_name = '/etc/network/interfaces.d/50-cloud-init.cfg'
            self.assertIn(eni_name, write_bufs)
            write_buf = write_bufs[eni_name]
            self.assertEqual(str(write_buf).strip(), V1_NET_CFG_OUTPUT.strip())
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_v1_to_netplan_ub(self):
        renderers = ['netplan']
        devlist = ['eth0', 'lo']
        ub_distro = self._get_distro('ubuntu', renderers=renderers)
        with ExitStack() as mocks:
            write_bufs = {}

            def replace_write(filename, content, mode=0o644, omode="wb"):
                buf = WriteBuffer()
                buf.mode = mode
                buf.omode = omode
                buf.write(content)
                write_bufs[filename] = buf

            mocks.enter_context(
                mock.patch.object(util, 'which', return_value=True))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'ensure_dir'))
            mocks.enter_context(
                mock.patch.object(util, 'subp', return_value=(0, 0)))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))
            mocks.enter_context(
                mock.patch("cloudinit.net.netplan.get_devicelist",
                           return_value=devlist))

            ub_distro.apply_network_config(V1_NET_CFG, False)

            self.assertEqual(len(write_bufs), 1)
            netplan_name = '/etc/netplan/50-cloud-init.yaml'
            self.assertIn(netplan_name, write_bufs)
            write_buf = write_bufs[netplan_name]
            self.assertEqual(str(write_buf).strip(),
                             V1_TO_V2_NET_CFG_OUTPUT.strip())
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_v2_passthrough_ub(self):
        renderers = ['netplan']
        devlist = ['eth0', 'lo']
        ub_distro = self._get_distro('ubuntu', renderers=renderers)
        with ExitStack() as mocks:
            write_bufs = {}

            def replace_write(filename, content, mode=0o644, omode="wb"):
                buf = WriteBuffer()
                buf.mode = mode
                buf.omode = omode
                buf.write(content)
                write_bufs[filename] = buf

            mocks.enter_context(
                mock.patch.object(util, 'which', return_value=True))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'ensure_dir'))
            mocks.enter_context(
                mock.patch.object(util, 'subp', return_value=(0, 0)))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))
            # FreeBSD does not have '/sys/class/net' file,
            # so we need mock here.
            mocks.enter_context(
                mock.patch.object(os, 'listdir', return_value=devlist))
            ub_distro.apply_network_config(V2_NET_CFG, False)

            self.assertEqual(len(write_bufs), 1)
            netplan_name = '/etc/netplan/50-cloud-init.yaml'
            self.assertIn(netplan_name, write_bufs)
            write_buf = write_bufs[netplan_name]
            self.assertEqual(str(write_buf).strip(),
                             V2_TO_V2_NET_CFG_OUTPUT.strip())
            self.assertEqual(write_buf.mode, 0o644)

    def assertCfgEquals(self, blob1, blob2):
        b1 = dict(SysConf(blob1.strip().splitlines()))
        b2 = dict(SysConf(blob2.strip().splitlines()))
        self.assertEqual(b1, b2)
        for (k, v) in b1.items():
            self.assertIn(k, b2)
        for (k, v) in b2.items():
            self.assertIn(k, b1)
        for (k, v) in b1.items():
            self.assertEqual(v, b2[k])

    @mock.patch('cloudinit.distros.freebsd.Distro.get_ifconfig_list')
    @mock.patch('cloudinit.distros.freebsd.Distro.get_ifconfig_ifname_out')
    def test_get_ip_nic_freebsd(self, ifname_out, iflist):
        frbsd_distro = self._get_distro('freebsd')
        iflist.return_value = "lo0 hn0"
        ifname_out.return_value = self.frbsd_ifout
        res = frbsd_distro.get_ipv4()
        self.assertEqual(res, ['lo0', 'hn0'])
        res = frbsd_distro.get_ipv6()
        self.assertEqual(res, [])

    @mock.patch('cloudinit.distros.freebsd.Distro.get_ifconfig_ether')
    @mock.patch('cloudinit.distros.freebsd.Distro.get_ifconfig_ifname_out')
    @mock.patch('cloudinit.distros.freebsd.Distro.get_interface_mac')
    def test_generate_fallback_config_freebsd(self, mac, ifname_out, if_ether):
        frbsd_distro = self._get_distro('freebsd')

        if_ether.return_value = 'hn0'
        ifname_out.return_value = self.frbsd_ifout
        mac.return_value = '00:15:5d:4c:73:00'
        res = frbsd_distro.generate_fallback_config()
        self.assertIsNotNone(res)

    def test_simple_write_rh(self):
        rh_distro = self._get_distro('rhel')

        write_bufs = {}

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        with ExitStack() as mocks:
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', return_value=''))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))

            rh_distro.apply_network(BASE_NET_CFG, False)

            self.assertEqual(len(write_bufs), 4)
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-lo',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-lo']
            expected_buf = '''
DEVICE="lo"
ONBOOT=yes
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth0',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth0']
            expected_buf = '''
DEVICE="eth0"
BOOTPROTO="static"
NETMASK="255.255.255.0"
IPADDR="192.168.1.5"
ONBOOT=yes
GATEWAY="192.168.1.254"
BROADCAST="192.168.1.0"
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth1',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth1']
            expected_buf = '''
DEVICE="eth1"
BOOTPROTO="dhcp"
ONBOOT=yes
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network', write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network']
            expected_buf = '''
# Created by cloud-init v. 0.7
NETWORKING=yes
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_rh(self):
        renderers = ['sysconfig']
        rh_distro = self._get_distro('rhel', renderers=renderers)

        write_bufs = {}

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        with ExitStack() as mocks:
            # sysconfig availability checks
            mocks.enter_context(
                mock.patch.object(util, 'which', return_value=True))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', return_value=''))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=True))

            rh_distro.apply_network_config(V1_NET_CFG, False)

            self.assertEqual(len(write_bufs), 5)

            # eth0
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth0',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth0']
            expected_buf = '''
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
GATEWAY=192.168.1.254
IPADDR=192.168.1.5
NETMASK=255.255.255.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            # eth1
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth1',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth1']
            expected_buf = '''
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network', write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network']
            expected_buf = '''
# Created by cloud-init v. 0.7
NETWORKING=yes
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_write_ipv6_rhel(self):
        rh_distro = self._get_distro('rhel')

        write_bufs = {}

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        with ExitStack() as mocks:
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', return_value=''))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=False))
            rh_distro.apply_network(BASE_NET_CFG_IPV6, False)

            self.assertEqual(len(write_bufs), 4)
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-lo',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-lo']
            expected_buf = '''
DEVICE="lo"
ONBOOT=yes
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth0',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth0']
            expected_buf = '''
DEVICE="eth0"
BOOTPROTO="static"
NETMASK="255.255.255.0"
IPADDR="192.168.1.5"
ONBOOT=yes
GATEWAY="192.168.1.254"
BROADCAST="192.168.1.0"
IPV6INIT=yes
IPV6ADDR="2607:f0d0:1002:0011::2"
IPV6_DEFAULTGW="2607:f0d0:1002:0011::1"
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth1',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth1']
            expected_buf = '''
DEVICE="eth1"
BOOTPROTO="static"
NETMASK="255.255.255.0"
IPADDR="192.168.1.6"
ONBOOT=no
GATEWAY="192.168.1.254"
BROADCAST="192.168.1.0"
IPV6INIT=yes
IPV6ADDR="2607:f0d0:1002:0011::3"
IPV6_DEFAULTGW="2607:f0d0:1002:0011::1"
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network', write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network']
            expected_buf = '''
# Created by cloud-init v. 0.7
NETWORKING=yes
NETWORKING_IPV6=yes
IPV6_AUTOCONF=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_ipv6_rh(self):
        renderers = ['sysconfig']
        rh_distro = self._get_distro('rhel', renderers=renderers)

        write_bufs = {}

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        with ExitStack() as mocks:
            mocks.enter_context(
                mock.patch.object(util, 'which', return_value=True))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', return_value=''))
            mocks.enter_context(
                mock.patch.object(os.path, 'isfile', return_value=True))

            rh_distro.apply_network_config(V1_NET_CFG_IPV6, False)

            self.assertEqual(len(write_bufs), 5)

            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth0',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth0']
            expected_buf = '''
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
IPV6ADDR=2607:f0d0:1002:0011::2/64
IPV6INIT=yes
IPV6_DEFAULTGW=2607:f0d0:1002:0011::1
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)
            self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth1',
                          write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth1']
            expected_buf = '''
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

            self.assertIn('/etc/sysconfig/network', write_bufs)
            write_buf = write_bufs['/etc/sysconfig/network']
            expected_buf = '''
# Created by cloud-init v. 0.7
NETWORKING=yes
NETWORKING_IPV6=yes
IPV6_AUTOCONF=no
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_simple_write_freebsd(self):
        fbsd_distro = self._get_distro('freebsd')

        write_bufs = {}
        read_bufs = {
            '/etc/rc.conf': '',
            '/etc/resolv.conf': '',
        }

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        def replace_read(fname, read_cb=None, quiet=False):
            if fname not in read_bufs:
                if fname in write_bufs:
                    return str(write_bufs[fname])
                raise IOError("%s not found" % fname)
            else:
                if fname in write_bufs:
                    return str(write_bufs[fname])
                return read_bufs[fname]

        with ExitStack() as mocks:
            mocks.enter_context(
                mock.patch.object(util, 'subp', return_value=('vtnet0', '')))
            mocks.enter_context(
                mock.patch.object(os.path, 'exists', return_value=False))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', replace_read))

            fbsd_distro.apply_network(BASE_NET_CFG, False)

            self.assertIn('/etc/rc.conf', write_bufs)
            write_buf = write_bufs['/etc/rc.conf']
            expected_buf = '''
ifconfig_vtnet0="192.168.1.5 netmask 255.255.255.0"
ifconfig_vtnet1="DHCP"
defaultrouter="192.168.1.254"
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_apply_network_config_fallback(self):
        fbsd_distro = self._get_distro('freebsd')

        # a weak attempt to verify that we don't have an implementation
        # of _write_network_config or apply_network_config in fbsd now,
        # which would make this test not actually test the fallback.
        self.assertRaises(
            NotImplementedError, fbsd_distro._write_network_config,
            BASE_NET_CFG)

        # now run
        mynetcfg = {
            'config': [{"type": "physical", "name": "eth0",
                        "mac_address": "c0:d6:9f:2c:e8:80",
                        "subnets": [{"type": "dhcp"}]}],
            'version': 1}

        write_bufs = {}
        read_bufs = {
            '/etc/rc.conf': '',
            '/etc/resolv.conf': '',
        }

        def replace_write(filename, content, mode=0o644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        def replace_read(fname, read_cb=None, quiet=False):
            if fname not in read_bufs:
                if fname in write_bufs:
                    return str(write_bufs[fname])
                raise IOError("%s not found" % fname)
            else:
                if fname in write_bufs:
                    return str(write_bufs[fname])
                return read_bufs[fname]

        with ExitStack() as mocks:
            mocks.enter_context(
                mock.patch.object(util, 'subp', return_value=('vtnet0', '')))
            mocks.enter_context(
                mock.patch.object(os.path, 'exists', return_value=False))
            mocks.enter_context(
                mock.patch.object(util, 'write_file', replace_write))
            mocks.enter_context(
                mock.patch.object(util, 'load_file', replace_read))

            fbsd_distro.apply_network_config(mynetcfg, bring_up=False)

            self.assertIn('/etc/rc.conf', write_bufs)
            write_buf = write_bufs['/etc/rc.conf']
            expected_buf = '''
ifconfig_vtnet0="DHCP"
'''
            self.assertCfgEquals(expected_buf, str(write_buf))
            self.assertEqual(write_buf.mode, 0o644)

    def test_simple_write_opensuse(self):
        """Opensuse network rendering writes appropriate sysconfg files."""
        tmpdir = self.tmp_dir()
        self.patchOS(tmpdir)
        self.patchUtils(tmpdir)
        distro = self._get_distro('opensuse')

        distro.apply_network(BASE_NET_CFG, False)

        lo_path = os.path.join(tmpdir, 'etc/sysconfig/network/ifcfg-lo')
        eth0_path = os.path.join(tmpdir, 'etc/sysconfig/network/ifcfg-eth0')
        eth1_path = os.path.join(tmpdir, 'etc/sysconfig/network/ifcfg-eth1')
        expected_cfgs = {
            lo_path: dedent('''
                STARTMODE="auto"
                USERCONTROL="no"
                FIREWALL="no"
                '''),
            eth0_path: dedent('''
                BOOTPROTO="static"
                BROADCAST="192.168.1.0"
                GATEWAY="192.168.1.254"
                IPADDR="192.168.1.5"
                NETMASK="255.255.255.0"
                STARTMODE="auto"
                USERCONTROL="no"
                ETHTOOL_OPTIONS=""
                '''),
            eth1_path: dedent('''
                BOOTPROTO="dhcp"
                STARTMODE="auto"
                USERCONTROL="no"
                ETHTOOL_OPTIONS=""
                ''')
        }
        for cfgpath in (lo_path, eth0_path, eth1_path):
            self.assertCfgEquals(
                expected_cfgs[cfgpath],
                util.load_file(cfgpath))
            file_stat = os.stat(cfgpath)
            self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))

# vi: ts=4 expandtab
