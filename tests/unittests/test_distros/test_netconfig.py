from mocker import MockerTestCase

import mocker

import os

from cloudinit import distros
from cloudinit import helpers
from cloudinit import settings
from cloudinit import util

from cloudinit.distros.parsers.sys_conf import SysConf

from StringIO import StringIO


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


class WriteBuffer(object):
    def __init__(self):
        self.buffer = StringIO()
        self.mode = None
        self.omode = None

    def write(self, text):
        self.buffer.write(text)

    def __str__(self):
        return self.buffer.getvalue()


class TestNetCfgDistro(MockerTestCase):

    def _get_distro(self, dname):
        cls = distros.fetch(dname)
        cfg = settings.CFG_BUILTIN
        cfg['system_info']['distro'] = dname
        paths = helpers.Paths({})
        return cls(dname, cfg, paths)

    def test_simple_write_ub(self):
        ub_distro = self._get_distro('ubuntu')
        util_mock = self.mocker.replace(util.write_file,
                                        spec=False, passthrough=False)
        exists_mock = self.mocker.replace(os.path.isfile,
                                          spec=False, passthrough=False)

        exists_mock(mocker.ARGS)
        self.mocker.count(0, None)
        self.mocker.result(False)

        write_bufs = {}

        def replace_write(filename, content, mode=0644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        util_mock(mocker.ARGS)
        self.mocker.call(replace_write)
        self.mocker.replay()
        ub_distro.apply_network(BASE_NET_CFG, False)

        self.assertEquals(len(write_bufs), 1)
        self.assertIn('/etc/network/interfaces', write_bufs)
        write_buf = write_bufs['/etc/network/interfaces']
        self.assertEquals(str(write_buf).strip(), BASE_NET_CFG.strip())
        self.assertEquals(write_buf.mode, 0644)

    def assertCfgEquals(self, blob1, blob2):
        b1 = dict(SysConf(blob1.strip().splitlines()))
        b2 = dict(SysConf(blob2.strip().splitlines()))
        self.assertEquals(b1, b2)
        for (k, v) in b1.items():
            self.assertIn(k, b2)
        for (k, v) in b2.items():
            self.assertIn(k, b1)
        for (k, v) in b1.items():
            self.assertEquals(v, b2[k])

    def test_simple_write_rh(self):
        rh_distro = self._get_distro('rhel')
        write_mock = self.mocker.replace(util.write_file,
                                         spec=False, passthrough=False)
        load_mock = self.mocker.replace(util.load_file,
                                        spec=False, passthrough=False)
        exists_mock = self.mocker.replace(os.path.isfile,
                                          spec=False, passthrough=False)

        write_bufs = {}

        def replace_write(filename, content, mode=0644, omode="wb"):
            buf = WriteBuffer()
            buf.mode = mode
            buf.omode = omode
            buf.write(content)
            write_bufs[filename] = buf

        exists_mock(mocker.ARGS)
        self.mocker.count(0, None)
        self.mocker.result(False)

        load_mock(mocker.ARGS)
        self.mocker.count(0, None)
        self.mocker.result('')

        for _i in range(0, 3):
            write_mock(mocker.ARGS)
            self.mocker.call(replace_write)

        write_mock(mocker.ARGS)
        self.mocker.call(replace_write)

        self.mocker.replay()
        rh_distro.apply_network(BASE_NET_CFG, False)

        self.assertEquals(len(write_bufs), 4)
        self.assertIn('/etc/sysconfig/network-scripts/ifcfg-lo', write_bufs)
        write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-lo']
        expected_buf = '''
DEVICE="lo"
ONBOOT=yes
'''
        self.assertCfgEquals(expected_buf, str(write_buf))
        self.assertEquals(write_buf.mode, 0644)

        self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth0', write_bufs)
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
        self.assertEquals(write_buf.mode, 0644)

        self.assertIn('/etc/sysconfig/network-scripts/ifcfg-eth1', write_bufs)
        write_buf = write_bufs['/etc/sysconfig/network-scripts/ifcfg-eth1']
        expected_buf = '''
DEVICE="eth1"
BOOTPROTO="dhcp"
ONBOOT=yes
'''
        self.assertCfgEquals(expected_buf, str(write_buf))
        self.assertEquals(write_buf.mode, 0644)

        self.assertIn('/etc/sysconfig/network', write_bufs)
        write_buf = write_bufs['/etc/sysconfig/network']
        expected_buf = '''
# Created by cloud-init v. 0.7
NETWORKING=yes
'''
        self.assertCfgEquals(expected_buf, str(write_buf))
        self.assertEquals(write_buf.mode, 0644)

    def test_simple_write_freebsd(self):
        fbsd_distro = self._get_distro('freebsd')
        util_mock = self.mocker.replace(util.write_file,
                                        spec=False, passthrough=False)
        exists_mock = self.mocker.replace(os.path.isfile,
                                          spec=False, passthrough=False)
        load_mock = self.mocker.replace(util.load_file,
                                        spec=False, passthrough=False)

        exists_mock(mocker.ARGS)
        self.mocker.count(0, None)
        self.mocker.result(False)

        write_bufs = {}
        read_bufs = {
            '/etc/rc.conf': '',
        }

        def replace_write(filename, content, mode=0644, omode="wb"):
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

        util_mock(mocker.ARGS)
        self.mocker.call(replace_write)
        self.mocker.count(0, None)

        load_mock(mocker.ARGS)
        self.mocker.call(replace_read)
        self.mocker.count(0, None)

        self.mocker.replay()
        fbsd_distro.apply_network(BASE_NET_CFG, False)

        self.assertIn('/etc/rc.conf', write_bufs)
        write_buf = write_bufs['/etc/rc.conf']
        expected_buf = '''
ifconfig_vtnet0="192.168.1.5 netmask 255.255.255.0"
ifconfig_vtnet1="DHCP"
defaultrouter="192.168.1.254"
'''
        self.assertCfgEquals(expected_buf, str(write_buf))
        self.assertEquals(write_buf.mode, 0644)

