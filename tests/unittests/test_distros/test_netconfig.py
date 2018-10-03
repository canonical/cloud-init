# This file is part of cloud-init. See LICENSE file for license information.

import os
from six import StringIO
from textwrap import dedent

try:
    from unittest import mock
except ImportError:
    import mock

from cloudinit import distros
from cloudinit.distros.parsers.sys_conf import SysConf
from cloudinit import helpers
from cloudinit import settings
from cloudinit.tests.helpers import (
    FilesystemMockingTestCase, dir2dict, populate_dir)
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

BASE_NET_CFG_FROM_V2 = '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5/24
    gateway 192.168.1.254

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

V1_NET_CFG_OUTPUT = """\
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


V1_TO_V2_NET_CFG_OUTPUT = """\
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


V2_TO_V2_NET_CFG_OUTPUT = """\
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


class TestNetCfgDistroBase(FilesystemMockingTestCase):

    def setUp(self):
        super(TestNetCfgDistroBase, self).setUp()
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


class TestNetCfgDistroFreebsd(TestNetCfgDistroBase):

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

    def test_simple_write_freebsd(self):
        fbsd_distro = self._get_distro('freebsd')

        rc_conf = '/etc/rc.conf'
        read_bufs = {
            rc_conf: 'initial-rc-conf-not-validated',
            '/etc/resolv.conf': 'initial-resolv-conf-not-validated',
        }

        tmpd = self.tmp_dir()
        populate_dir(tmpd, read_bufs)
        with self.reRooted(tmpd):
            with mock.patch("cloudinit.distros.freebsd.util.subp",
                            return_value=('vtnet0', '')):
                fbsd_distro.apply_network(BASE_NET_CFG, False)
                results = dir2dict(tmpd)

        self.assertIn(rc_conf, results)
        self.assertCfgEquals(
            dedent('''\
                ifconfig_vtnet0="192.168.1.5 netmask 255.255.255.0"
                ifconfig_vtnet1="DHCP"
                defaultrouter="192.168.1.254"
                '''), results[rc_conf])
        self.assertEqual(0o644, get_mode(rc_conf, tmpd))

    def test_simple_write_freebsd_from_v2eni(self):
        fbsd_distro = self._get_distro('freebsd')

        rc_conf = '/etc/rc.conf'
        read_bufs = {
            rc_conf: 'initial-rc-conf-not-validated',
            '/etc/resolv.conf': 'initial-resolv-conf-not-validated',
        }

        tmpd = self.tmp_dir()
        populate_dir(tmpd, read_bufs)
        with self.reRooted(tmpd):
            with mock.patch("cloudinit.distros.freebsd.util.subp",
                            return_value=('vtnet0', '')):
                fbsd_distro.apply_network(BASE_NET_CFG_FROM_V2, False)
                results = dir2dict(tmpd)

        self.assertIn(rc_conf, results)
        self.assertCfgEquals(
            dedent('''\
                ifconfig_vtnet0="192.168.1.5 netmask 255.255.255.0"
                ifconfig_vtnet1="DHCP"
                defaultrouter="192.168.1.254"
                '''), results[rc_conf])
        self.assertEqual(0o644, get_mode(rc_conf, tmpd))

    def test_apply_network_config_fallback_freebsd(self):
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

        rc_conf = '/etc/rc.conf'
        read_bufs = {
            rc_conf: 'initial-rc-conf-not-validated',
            '/etc/resolv.conf': 'initial-resolv-conf-not-validated',
        }

        tmpd = self.tmp_dir()
        populate_dir(tmpd, read_bufs)
        with self.reRooted(tmpd):
            with mock.patch("cloudinit.distros.freebsd.util.subp",
                            return_value=('vtnet0', '')):
                fbsd_distro.apply_network_config(mynetcfg, bring_up=False)
                results = dir2dict(tmpd)

        self.assertIn(rc_conf, results)
        self.assertCfgEquals('ifconfig_vtnet0="DHCP"', results[rc_conf])
        self.assertEqual(0o644, get_mode(rc_conf, tmpd))


class TestNetCfgDistroUbuntuEni(TestNetCfgDistroBase):

    def setUp(self):
        super(TestNetCfgDistroUbuntuEni, self).setUp()
        self.distro = self._get_distro('ubuntu', renderers=['eni'])

    def eni_path(self):
        return '/etc/network/interfaces.d/50-cloud-init.cfg'

    def _apply_and_verify_eni(self, apply_fn, config, expected_cfgs=None,
                              bringup=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.eni.available') as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def test_apply_network_config_eni_ub(self):
        expected_cfgs = {
            self.eni_path(): V1_NET_CFG_OUTPUT,
        }
        # ub_distro.apply_network_config(V1_NET_CFG, False)
        self._apply_and_verify_eni(self.distro.apply_network_config,
                                   V1_NET_CFG,
                                   expected_cfgs=expected_cfgs.copy())


class TestNetCfgDistroUbuntuNetplan(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroUbuntuNetplan, self).setUp()
        self.distro = self._get_distro('ubuntu', renderers=['netplan'])
        self.devlist = ['eth0', 'lo']

    def _apply_and_verify_netplan(self, apply_fn, config, expected_cfgs=None,
                                  bringup=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.netplan.available',
                        return_value=True):
            with mock.patch("cloudinit.net.netplan.get_devicelist",
                            return_value=self.devlist):
                with self.reRooted(tmpd) as tmpd:
                    apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def netplan_path(self):
            return '/etc/netplan/50-cloud-init.yaml'

    def test_apply_network_config_v1_to_netplan_ub(self):
        expected_cfgs = {
            self.netplan_path(): V1_TO_V2_NET_CFG_OUTPUT,
        }

        # ub_distro.apply_network_config(V1_NET_CFG, False)
        self._apply_and_verify_netplan(self.distro.apply_network_config,
                                       V1_NET_CFG,
                                       expected_cfgs=expected_cfgs.copy())

    def test_apply_network_config_v2_passthrough_ub(self):
        expected_cfgs = {
            self.netplan_path(): V2_TO_V2_NET_CFG_OUTPUT,
        }
        # ub_distro.apply_network_config(V2_NET_CFG, False)
        self._apply_and_verify_netplan(self.distro.apply_network_config,
                                       V2_NET_CFG,
                                       expected_cfgs=expected_cfgs.copy())


class TestNetCfgDistroRedhat(TestNetCfgDistroBase):

    def setUp(self):
        super(TestNetCfgDistroRedhat, self).setUp()
        self.distro = self._get_distro('rhel', renderers=['sysconfig'])

    def ifcfg_path(self, ifname):
        return '/etc/sysconfig/network-scripts/ifcfg-%s' % ifname

    def control_path(self):
        return '/etc/sysconfig/network'

    def _apply_and_verify(self, apply_fn, config, expected_cfgs=None,
                          bringup=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.sysconfig.available') as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            self.assertCfgEquals(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def test_apply_network_config_rh(self):
        expected_cfgs = {
            self.ifcfg_path('eth0'): dedent("""\
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
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            self.control_path(): dedent("""\
                NETWORKING=yes
                """),
        }
        # rh_distro.apply_network_config(V1_NET_CFG, False)
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG,
                               expected_cfgs=expected_cfgs.copy())

    def test_apply_network_config_ipv6_rh(self):
        expected_cfgs = {
            self.ifcfg_path('eth0'): dedent("""\
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
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            self.control_path(): dedent("""\
                NETWORKING=yes
                NETWORKING_IPV6=yes
                IPV6_AUTOCONF=no
                """),
            }
        # rh_distro.apply_network_config(V1_NET_CFG_IPV6, False)
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG_IPV6,
                               expected_cfgs=expected_cfgs.copy())


class TestNetCfgDistroOpensuse(TestNetCfgDistroBase):

    def setUp(self):
        super(TestNetCfgDistroOpensuse, self).setUp()
        self.distro = self._get_distro('opensuse', renderers=['sysconfig'])

    def ifcfg_path(self, ifname):
        return '/etc/sysconfig/network/ifcfg-%s' % ifname

    def _apply_and_verify(self, apply_fn, config, expected_cfgs=None,
                          bringup=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.sysconfig.available') as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            self.assertCfgEquals(expected, results[cfgpath])
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    def test_apply_network_config_opensuse(self):
        """Opensuse uses apply_network_config and renders sysconfig"""
        expected_cfgs = {
            self.ifcfg_path('eth0'): dedent("""\
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
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
        }
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG,
                               expected_cfgs=expected_cfgs.copy())

    def test_apply_network_config_ipv6_opensuse(self):
        """Opensuse uses apply_network_config and renders sysconfig w/ipv6"""
        expected_cfgs = {
            self.ifcfg_path('eth0'): dedent("""\
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
            """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """),
        }
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG_IPV6,
                               expected_cfgs=expected_cfgs.copy())


def get_mode(path, target=None):
    return os.stat(util.target_path(target, path)).st_mode & 0o777

# vi: ts=4 expandtab
