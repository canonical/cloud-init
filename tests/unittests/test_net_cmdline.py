# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.net import cmdline
from cloudinit import temp_utils
from cloudinit import util

from cloudinit.tests.helpers import (
    CiTestCase, FilesystemMockingTestCase, mock, populate_dir)

import base64
import copy
import gzip
import io
import json
import os


DHCP_CONTENT_1 = """
DEVICE='eth0'
PROTO='dhcp'
IPV4ADDR='192.168.122.89'
IPV4BROADCAST='192.168.122.255'
IPV4NETMASK='255.255.255.0'
IPV4GATEWAY='192.168.122.1'
IPV4DNS0='192.168.122.1'
IPV4DNS1='0.0.0.0'
HOSTNAME='foohost'
DNSDOMAIN=''
NISDOMAIN=''
ROOTSERVER='192.168.122.1'
ROOTPATH=''
filename=''
UPTIME='21'
DHCPLEASETIME='3600'
DOMAINSEARCH='foo.com'
"""

DHCP_EXPECTED_1 = {
    'name': 'eth0',
    'type': 'physical',
    'subnets': [{'broadcast': '192.168.122.255',
                 'control': 'manual',
                 'gateway': '192.168.122.1',
                 'dns_search': ['foo.com'],
                 'type': 'dhcp',
                 'netmask': '255.255.255.0',
                 'dns_nameservers': ['192.168.122.1']}],
}

DHCP6_CONTENT_1 = """
DEVICE6=eno1
HOSTNAME=
DNSDOMAIN=
IPV6PROTO=dhcp6
IPV6ADDR=2001:67c:1562:8010:0:1::
IPV6NETMASK=64
IPV6DNS0=2001:67c:1562:8010::2:1
IPV6DOMAINSEARCH=
HOSTNAME=
DNSDOMAIN=
"""

DHCP6_EXPECTED_1 = {
    'name': 'eno1',
    'type': 'physical',
    'subnets': [{'control': 'manual',
                 'dns_nameservers': ['2001:67c:1562:8010::2:1'],
                 'netmask': '64',
                 'type': 'dhcp6'}]}


STATIC_CONTENT_1 = """
DEVICE='eth1'
PROTO='none'
IPV4ADDR='10.0.0.2'
IPV4BROADCAST='10.0.0.255'
IPV4NETMASK='255.255.255.0'
IPV4GATEWAY='10.0.0.1'
IPV4DNS0='10.0.1.1'
IPV4DNS1='0.0.0.0'
HOSTNAME='foohost'
UPTIME='21'
DHCPLEASETIME='3600'
DOMAINSEARCH='foo.com'
"""

STATIC_EXPECTED_1 = {
    'name': 'eth1',
    'type': 'physical',
    'subnets': [{'broadcast': '10.0.0.255', 'control': 'manual',
                 'gateway': '10.0.0.1',
                 'dns_search': ['foo.com'], 'type': 'static',
                 'netmask': '255.255.255.0',
                 'dns_nameservers': ['10.0.1.1'],
                 'address': '10.0.0.2'}],
}

VLAN_STATIC_CONTENT_1 = """
DEVICE='ens3.2653'
PROTO='none'
IPV4ADDR='10.245.236.14'
IPV4BROADCAST='10.245.236.255'
IPV4NETMASK='255.255.255.0'
IPV4GATEWAY='10.245.236.1'
IPV4DNS0='10.245.236.1'
IPV4DNS1='0.0.0.0'
HOSTNAME='s1lp14'
DNSDOMAIN=''
NISDOMAIN=''
ROOTSERVER='0.0.0.0'
ROOTPATH=''
filename=''
UPTIME='4'
DHCPLEASETIME='0'
DOMAINSEARCH=''
"""

VLAN_STATIC_EXPECTED_1 = {
    'name': 'ens3', 'type': 'physical',
    'subnets': [{'type': 'static', 'control': 'manual'}],
}

VLAN_STATIC_EXPECTED_2 = {
    'name': 'ens3.2653', 'type': 'vlan',
    'vlan_id': '2653', 'vlan_link': 'ens3',
    'subnets': [{'address': '10.245.236.14',
                 'broadcast': '10.245.236.255',
                 'dns_nameservers': ['10.245.236.1'],
                 'gateway': '10.245.236.1',
                 'netmask': '255.255.255.0',
                 'control': 'manual',
                 'type': 'static'}],
}

NETPLAN_DHCP_CONTENT_1 = """\
network:
  version: 2
  ethernets:
      ens3:
         dhcp4: true
         match:
           macaddress: 00:11:22:33:44:55
         set-name: ens3
"""

NETPLAN_DHCP_CONTENT_2 = """\
network:
  version: 2
  ethernets:
      ens5:
         dhcp4: false
         dhcp6: true
         match:
           macaddress: aa:bb:cc:dd:ee:ff
         set-name: ens5
"""

NETPLAN_DHCP_CONTENT_3 = """\
network:
  version: 2
  ethernets:
      ens3:
         dhcp4: false
         match:
           macaddress: 00:11:22:33:44:55
         set-name: mgmt3
"""

NETPLAN_DHCP_EXPECTED_1 = {
    'version': 2,
    'ethernets': {
        'ens3': {
            'dhcp4': True,
            'match': {'macaddress': '00:11:22:33:44:55'},
            'set-name': 'ens3'
        },
    },
}

NETPLAN_DHCP_EXPECTED_1_2 = {
    'version': 2,
    'ethernets': {
        'ens3': {
            'dhcp4': True,
            'match': {'macaddress': '00:11:22:33:44:55'},
            'set-name': 'ens3'
        },
        'ens5': {
            'dhcp4': False,
            'dhcp6': True,
            'match': {'macaddress': 'aa:bb:cc:dd:ee:ff'},
            'set-name': 'ens5'
        },
    }
}

NETPLAN_DHCP_EXPECTED_1_2_3 = {
    'version': 2,
    'ethernets': {
        'ens3': {
            'dhcp4': False,
            'match': {'macaddress': '00:11:22:33:44:55'},
            'set-name': 'mgmt3'
        },
        'ens5': {
            'dhcp4': False,
            'dhcp6': True,
            'match': {'macaddress': 'aa:bb:cc:dd:ee:ff'},
            'set-name': 'ens5'
        },
    }
}


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()


class TestCmdlineConfigParsing(CiTestCase):
    with_logs = True

    simple_cfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}]}

    def test_cmdline_convert_dhcp(self):
        found = cmdline._klibc_to_config_entry(DHCP_CONTENT_1)
        self.assertEqual(found, [('eth0', DHCP_EXPECTED_1)])

    def test_cmdline_convert_dhcp6(self):
        found = cmdline._klibc_to_config_entry(DHCP6_CONTENT_1)
        self.assertEqual(found, [('eno1', DHCP6_EXPECTED_1)])

    def test_cmdline_convert_static(self):
        found = cmdline._klibc_to_config_entry(STATIC_CONTENT_1)
        self.assertEqual(found, [('eth1', STATIC_EXPECTED_1)])

    def test_cmdline_convert_static_vlan(self):
        found = cmdline._klibc_to_config_entry(VLAN_STATIC_CONTENT_1)
        self.assertEqual(found[0], ('ens3', VLAN_STATIC_EXPECTED_1))
        self.assertEqual(found[1], ('ens3.2653', VLAN_STATIC_EXPECTED_2))

    def test_config_from_cmdline_net_cfg(self):
        files = []
        pairs = (('net-eth0.cfg', DHCP_CONTENT_1),
                 ('net-eth1.cfg', STATIC_CONTENT_1))

        macs = {'eth1': 'b8:ae:ed:75:ff:2b',
                'eth0': 'b8:ae:ed:75:ff:2a'}

        dhcp = copy.deepcopy(DHCP_EXPECTED_1)
        dhcp['mac_address'] = macs['eth0']

        static = copy.deepcopy(STATIC_EXPECTED_1)
        static['mac_address'] = macs['eth1']

        expected = {'version': 1, 'config': [dhcp, static]}
        with temp_utils.tempdir() as tmpd:
            for fname, content in pairs:
                fp = os.path.join(tmpd, fname)
                files.append(fp)
                util.write_file(fp, content)

            found = cmdline.config_from_klibc_net_cfg(files=files,
                                                      mac_addrs=macs)
            self.assertEqual(found, expected)

    def test_cmdline_with_b64(self):
        data = base64.b64encode(json.dumps(self.simple_cfg).encode())
        encoded_text = data.decode()
        raw_cmdline = 'ro network-config=' + encoded_text + ' root=foo'
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        self.assertEqual(found, self.simple_cfg)

    def test_cmdline_with_net_config_disabled(self):
        raw_cmdline = 'ro network-config=disabled root=foo'
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        self.assertEqual(found, {'config': 'disabled'})

    def test_cmdline_with_net_config_unencoded_logs_error(self):
        """network-config cannot be unencoded besides 'disabled'."""
        raw_cmdline = 'ro network-config={config:disabled} root=foo'
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        self.assertIsNone(found)
        expected_log = (
            'ERROR: Expected base64 encoded kernel commandline parameter'
            ' network-config. Ignoring network-config={config:disabled}.')
        self.assertIn(expected_log, self.logs.getvalue())

    def test_cmdline_with_b64_gz(self):
        data = _gzip_data(json.dumps(self.simple_cfg).encode())
        encoded_text = base64.b64encode(data).decode()
        raw_cmdline = 'ro network-config=' + encoded_text + ' root=foo'
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        self.assertEqual(found, self.simple_cfg)


class TestCmdlineKlibcNetworkConfigSource(FilesystemMockingTestCase):
    macs = {
        'eth0': '14:02:ec:42:48:00',
        'eno1': '14:02:ec:42:48:01',
    }

    def test_without_ip(self):
        content = {'/run/net-eth0.conf': DHCP_CONTENT_1,
                   cmdline._OPEN_ISCSI_INTERFACE_FILE: "eth0\n"}
        exp1 = copy.deepcopy(DHCP_EXPECTED_1)
        exp1['mac_address'] = self.macs['eth0']

        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline='foo root=/root/bar', _mac_addrs=self.macs,
        )
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(found['version'], 1)
        self.assertEqual(found['config'], [exp1])

    def test_with_ip(self):
        content = {'/run/net-eth0.conf': DHCP_CONTENT_1}
        exp1 = copy.deepcopy(DHCP_EXPECTED_1)
        exp1['mac_address'] = self.macs['eth0']

        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline='foo ip=dhcp', _mac_addrs=self.macs,
        )
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(found['version'], 1)
        self.assertEqual(found['config'], [exp1])

    def test_with_ip6(self):
        content = {'/run/net6-eno1.conf': DHCP6_CONTENT_1}
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline='foo ip6=dhcp root=/dev/sda', _mac_addrs=self.macs,
        )
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(
            found,
            {'version': 1, 'config': [
             {'type': 'physical', 'name': 'eno1',
              'mac_address': self.macs['eno1'],
              'subnets': [
                  {'dns_nameservers': ['2001:67c:1562:8010::2:1'],
                   'control': 'manual', 'type': 'dhcp6', 'netmask': '64'}]}]})

    def test_with_no_ip_or_ip6(self):
        # if there is no ip= or ip6= on cmdline, return value should be None
        content = {'net6-eno1.conf': DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files, _cmdline='foo root=/dev/sda', _mac_addrs=self.macs,
        )
        self.assertFalse(src.is_applicable())

    def test_with_both_ip_ip6(self):
        content = {
            '/run/net-eth0.conf': DHCP_CONTENT_1,
            '/run/net6-eth0.conf': DHCP6_CONTENT_1.replace('eno1', 'eth0')}
        eth0 = copy.deepcopy(DHCP_EXPECTED_1)
        eth0['mac_address'] = self.macs['eth0']
        eth0['subnets'].append(
            {'control': 'manual', 'type': 'dhcp6',
             'netmask': '64', 'dns_nameservers': ['2001:67c:1562:8010::2:1']})
        expected = [eth0]

        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline='foo ip=dhcp ip6=dhcp', _mac_addrs=self.macs,
        )

        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(found['version'], 1)
        self.assertEqual(found['config'], expected)


class TestNetplanConfigSource(FilesystemMockingTestCase):

    maxDiff = None
    with_logs = True

    def test_netplan_single_file(self):
        content = {'/run/netplan/ens3.yaml': NETPLAN_DHCP_CONTENT_1}
        expected = copy.deepcopy(NETPLAN_DHCP_EXPECTED_1)
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(expected, found)

    def test_netplan_multiple_files(self):
        content = {
            '/run/netplan/ens3.yaml': NETPLAN_DHCP_CONTENT_1,
            '/run/netplan/ens5.yaml': NETPLAN_DHCP_CONTENT_2,
        }
        expected = copy.deepcopy(NETPLAN_DHCP_EXPECTED_1_2)
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(expected, found)

    def test_netplan_multiple_files_with_overlap(self):
        content = {
            '/run/netplan/ens3.yaml': NETPLAN_DHCP_CONTENT_1,
            '/run/netplan/ens5.yaml': NETPLAN_DHCP_CONTENT_2,
            '/run/netplan/99-mgmt.yaml': NETPLAN_DHCP_CONTENT_3,
        }
        expected = copy.deepcopy(NETPLAN_DHCP_EXPECTED_1_2_3)
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(expected, found)

    def test_netplan_bad_file(self):
        content = {'/run/netplan/ens3.yaml': self.random_string()}
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual({}, found)

    def test_netplan_multiple_files_with_bad_files(self):
        content = {
            '/run/netplan/ens2.yaml': self.random_string(),
            '/run/netplan/ens3.yaml': NETPLAN_DHCP_CONTENT_1,
            '/run/netplan/ens4.yaml': self.random_string(),
            '/run/netplan/ens5.yaml': NETPLAN_DHCP_CONTENT_2,
            '/run/netplan/ens7.yaml': self.random_string(),
        }
        expected = copy.deepcopy(NETPLAN_DHCP_EXPECTED_1_2)
        root = self.tmp_dir()
        populate_dir(root, content)
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertTrue(src.is_applicable())
        found = src.render_config()
        self.assertEqual(expected, found)

    def test_netplan_no_files(self):
        root = self.tmp_dir()
        self.reRoot(root)
        src = cmdline.NetplanConfigSource()
        self.assertFalse(src.is_applicable())
        self.assertEqual({}, src.render_config())


class TestReadInitramfsConfig(CiTestCase):

    def _config_source_cls_mock(self, is_applicable, render_config=None):
        return lambda: mock.Mock(
            is_applicable=lambda: is_applicable,
            render_config=lambda: render_config,
        )

    def test_no_sources(self):
        with mock.patch('cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES', []):
            self.assertIsNone(cmdline.read_initramfs_config())

    def test_no_applicable_sources(self):
        sources = [
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
        ]
        with mock.patch('cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES',
                        sources):
            self.assertIsNone(cmdline.read_initramfs_config())

    def test_one_applicable_source(self):
        expected_config = object()
        sources = [
            self._config_source_cls_mock(
                is_applicable=True, render_config=expected_config,
            ),
        ]
        with mock.patch('cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES',
                        sources):
            self.assertEqual(expected_config, cmdline.read_initramfs_config())

    def test_one_applicable_source_after_inapplicable_sources(self):
        expected_config = object()
        sources = [
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(
                is_applicable=True, render_config=expected_config,
            ),
        ]
        with mock.patch('cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES',
                        sources):
            self.assertEqual(expected_config, cmdline.read_initramfs_config())

    def test_first_applicable_source_is_used(self):
        first_config, second_config = object(), object()
        sources = [
            self._config_source_cls_mock(
                is_applicable=True, render_config=first_config,
            ),
            self._config_source_cls_mock(
                is_applicable=True, render_config=second_config,
            ),
        ]
        with mock.patch('cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES',
                        sources):
            self.assertEqual(first_config, cmdline.read_initramfs_config())

# vi: ts=4 expandtab
