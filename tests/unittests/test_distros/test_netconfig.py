# This file is part of cloud-init. See LICENSE file for license information.

import copy
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
    FilesystemMockingTestCase, dir2dict)
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
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
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
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
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
# This file is generated from information provided by the datasource.  Changes
# to it will not persist across an instance reboot.  To disable cloud-init's
# network configuration capabilities, write a file
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


class TestNetCfgDistroFreeBSD(TestNetCfgDistroBase):

    def setUp(self):
        super(TestNetCfgDistroFreeBSD, self).setUp()
        self.distro = self._get_distro('freebsd', renderers=['freebsd'])

    def _apply_and_verify_freebsd(self, apply_fn, config, expected_cfgs=None,
                                  bringup=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.freebsd.available') as m_avail:
            m_avail.return_value = True
            with self.reRooted(tmpd) as tmpd:
                util.ensure_dir('/etc')
                util.ensure_file('/etc/rc.conf')
                util.ensure_file('/etc/resolv.conf')
                apply_fn(config, bringup)

        results = dir2dict(tmpd)
        for cfgpath, expected in expected_cfgs.items():
            print("----------")
            print(expected)
            print("^^^^ expected | rendered VVVVVVV")
            print(results[cfgpath])
            print("----------")
            self.assertEqual(
                set(expected.split('\n')),
                set(results[cfgpath].split('\n')))
            self.assertEqual(0o644, get_mode(cfgpath, tmpd))

    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    def test_apply_network_config_freebsd_standard(self, ifaces_mac):
        ifaces_mac.return_value = {
            '00:15:5d:4c:73:00': 'eth0',
        }
        rc_conf_expected = """\
defaultrouter=192.168.1.254
ifconfig_eth0='192.168.1.5 netmask 255.255.255.0'
ifconfig_eth1=DHCP
"""

        expected_cfgs = {
            '/etc/rc.conf': rc_conf_expected,
            '/etc/resolv.conf': ''
        }
        self._apply_and_verify_freebsd(self.distro.apply_network_config,
                                       V1_NET_CFG,
                                       expected_cfgs=expected_cfgs.copy())

    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    def test_apply_network_config_freebsd_ifrename(self, ifaces_mac):
        ifaces_mac.return_value = {
            '00:15:5d:4c:73:00': 'vtnet0',
        }
        rc_conf_expected = """\
ifconfig_vtnet0_name=eth0
defaultrouter=192.168.1.254
ifconfig_eth0='192.168.1.5 netmask 255.255.255.0'
ifconfig_eth1=DHCP
"""

        V1_NET_CFG_RENAME = copy.deepcopy(V1_NET_CFG)
        V1_NET_CFG_RENAME['config'][0]['mac_address'] = '00:15:5d:4c:73:00'

        expected_cfgs = {
            '/etc/rc.conf': rc_conf_expected,
            '/etc/resolv.conf': ''
        }
        self._apply_and_verify_freebsd(self.distro.apply_network_config,
                                       V1_NET_CFG_RENAME,
                                       expected_cfgs=expected_cfgs.copy())

    @mock.patch('cloudinit.net.get_interfaces_by_mac')
    def test_apply_network_config_freebsd_nameserver(self, ifaces_mac):
        ifaces_mac.return_value = {
            '00:15:5d:4c:73:00': 'eth0',
        }

        V1_NET_CFG_DNS = copy.deepcopy(V1_NET_CFG)
        ns = ['1.2.3.4']
        V1_NET_CFG_DNS['config'][0]['subnets'][0]['dns_nameservers'] = ns
        expected_cfgs = {
            '/etc/resolv.conf': 'nameserver 1.2.3.4\n'
        }
        self._apply_and_verify_freebsd(self.distro.apply_network_config,
                                       V1_NET_CFG_DNS,
                                       expected_cfgs=expected_cfgs.copy())


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
                STARTMODE=auto
                TYPE=Ethernet
                USERCTL=no
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
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
                IPADDR6=2607:f0d0:1002:0011::2/64
                IPV6ADDR=2607:f0d0:1002:0011::2/64
                IPV6INIT=yes
                IPV6_DEFAULTGW=2607:f0d0:1002:0011::1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
                TYPE=Ethernet
                USERCTL=no
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
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
                STARTMODE=auto
                TYPE=Ethernet
                USERCTL=no
                """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
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
                IPADDR6=2607:f0d0:1002:0011::2/64
                IPV6ADDR=2607:f0d0:1002:0011::2/64
                IPV6INIT=yes
                IPV6_DEFAULTGW=2607:f0d0:1002:0011::1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
                TYPE=Ethernet
                USERCTL=no
            """),
            self.ifcfg_path('eth1'): dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth1
                NM_CONTROLLED=no
                ONBOOT=yes
                STARTMODE=auto
                TYPE=Ethernet
                USERCTL=no
            """),
        }
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG_IPV6,
                               expected_cfgs=expected_cfgs.copy())


class TestNetCfgDistroArch(TestNetCfgDistroBase):
    def setUp(self):
        super(TestNetCfgDistroArch, self).setUp()
        self.distro = self._get_distro('arch', renderers=['netplan'])

    def _apply_and_verify(self, apply_fn, config, expected_cfgs=None,
                          bringup=False, with_netplan=False):
        if not expected_cfgs:
            raise ValueError('expected_cfg must not be None')

        tmpd = None
        with mock.patch('cloudinit.net.netplan.available',
                        return_value=with_netplan):
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

    def netctl_path(self, iface):
        return '/etc/netctl/%s' % iface

    def netplan_path(self):
        return '/etc/netplan/50-cloud-init.yaml'

    def test_apply_network_config_v1_without_netplan(self):
        # Note that this is in fact an invalid netctl config:
        #  "Address=None/None"
        # But this is what the renderer has been writing out for a long time,
        # and the test's purpose is to assert that the netctl renderer is
        # still being used in absence of netplan, not the correctness of the
        # rendered netctl config.
        expected_cfgs = {
            self.netctl_path('eth0'): dedent("""\
                Address=192.168.1.5/255.255.255.0
                Connection=ethernet
                DNS=()
                Gateway=192.168.1.254
                IP=static
                Interface=eth0
                """),
            self.netctl_path('eth1'): dedent("""\
                Address=None/None
                Connection=ethernet
                DNS=()
                Gateway=
                IP=dhcp
                Interface=eth1
                """),
            }

        # ub_distro.apply_network_config(V1_NET_CFG, False)
        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG,
                               expected_cfgs=expected_cfgs.copy(),
                               with_netplan=False)

    def test_apply_network_config_v1_with_netplan(self):
        expected_cfgs = {
            self.netplan_path(): dedent("""\
                # generated by cloud-init
                network:
                    version: 2
                    ethernets:
                        eth0:
                            addresses:
                            - 192.168.1.5/24
                            gateway4: 192.168.1.254
                        eth1:
                            dhcp4: true
                """),
        }

        self._apply_and_verify(self.distro.apply_network_config,
                               V1_NET_CFG,
                               expected_cfgs=expected_cfgs.copy(),
                               with_netplan=True)


def get_mode(path, target=None):
    return os.stat(util.target_path(target, path)).st_mode & 0o777

# vi: ts=4 expandtab
