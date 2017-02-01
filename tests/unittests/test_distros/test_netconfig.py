# This file is part of cloud-init. See LICENSE file for license information.

import os
from six import StringIO

try:
    from unittest import mock
except ImportError:
    import mock
try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

from ..helpers import TestCase

from cloudinit import distros
from cloudinit.distros.parsers.sys_conf import SysConf
from cloudinit import helpers
from cloudinit import settings
from cloudinit import util


BASE_NET_CFG = '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.5
    netmask 255.255.255.0
    network 192.168.0.0
    broadcast 192.168.1.0
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


class WriteBuffer(object):
    def __init__(self):
        self.buffer = StringIO()
        self.mode = None
        self.omode = None

    def write(self, text):
        self.buffer.write(text)

    def __str__(self):
        return self.buffer.getvalue()


class TestNetCfgDistro(TestCase):

    def _get_distro(self, dname):
        cls = distros.fetch(dname)
        cfg = settings.CFG_BUILTIN
        cfg['system_info']['distro'] = dname
        paths = helpers.Paths({})
        return cls(dname, cfg, paths)

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

# vi: ts=4 expandtab
