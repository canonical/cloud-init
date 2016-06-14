from cloudinit import net
from cloudinit.net import cmdline
from cloudinit.net import eni
from cloudinit.net import network_state
from cloudinit.net import sysconfig
from cloudinit.sources.helpers import openstack
from cloudinit import util

from .helpers import mock
from .helpers import TestCase

import base64
import copy
import gzip
import io
import json
import os
import shutil
import tempfile

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


STATIC_CONTENT_1 = """
DEVICE='eth1'
PROTO='static'
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
                 'dns_nameservers': ['10.0.1.1']}],
}

# Examples (and expected outputs for various renderers).
OS_SAMPLES = [
    {
        'in_data': {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [{
                "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                "type": "ipv4", "netmask": "255.255.252.0",
                "link": "tap1a81968a-79",
                "routes": [{
                    "netmask": "0.0.0.0",
                    "network": "0.0.0.0",
                    "gateway": "172.19.3.254",
                }],
                "ip_address": "172.19.1.34", "id": "network0"
            }],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None, "type": "bridge", "id":
                    "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f"
                },
            ],
        },
        'in_macs': {
            'fa:16:3e:ed:9a:59': 'eth0',
        },
        'out_sysconfig': [
            ('etc/sysconfig/network-scripts/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=static
DEFROUTE=yes
DEVICE=eth0
GATEWAY=172.19.3.254
HWADDR=fa:16:3e:ed:9a:59
IPADDR=172.19.1.34
NETMASK=255.255.252.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()),
            ('etc/sysconfig/network-scripts/route-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
ADDRESS0=0.0.0.0
GATEWAY0=172.19.3.254
NETMASK0=0.0.0.0
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/udev/rules.d/70-persistent-net.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))]
    }
]


def _setup_test(tmp_dir, mock_get_devicelist, mock_sys_netdev_info,
                mock_sys_dev_path):
    mock_get_devicelist.return_value = ['eth1000']
    dev_characteristics = {
        'eth1000': {
            "bridge": False,
            "carrier": False,
            "dormant": False,
            "operstate": "down",
            "address": "07-1C-C6-75-A4-BE",
        }
    }

    def netdev_info(name, field):
        return dev_characteristics[name][field]

    mock_sys_netdev_info.side_effect = netdev_info

    def sys_dev_path(devname, path=""):
        return tmp_dir + devname + "/" + path

    for dev in dev_characteristics:
        os.makedirs(os.path.join(tmp_dir, dev))
        with open(os.path.join(tmp_dir, dev, 'operstate'), 'w') as fh:
            fh.write("down")

    mock_sys_dev_path.side_effect = sys_dev_path


class TestSysConfigRendering(TestCase):

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.sys_netdev_info")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_sys_netdev_info,
                                mock_sys_dev_path):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir)
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_sys_netdev_info, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = sysconfig.Renderer()
        renderer.render_network_state(render_dir, ns)

        render_file = 'etc/sysconfig/network-scripts/ifcfg-eth1000'
        with open(os.path.join(render_dir, render_file)) as fh:
            content = fh.read()
            expected_content = """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1000
HWADDR=07-1C-C6-75-A4-BE
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()
            self.assertEqual(expected_content, content)

    def test_openstack_rendering_samples(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir)
        render_dir = os.path.join(tmp_dir, "render")
        for os_sample in OS_SAMPLES:
            ex_input = os_sample['in_data']
            ex_mac_addrs = os_sample['in_macs']
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs)
            ns = network_state.parse_net_config_data(network_cfg,
                                                     skip_broken=False)
            renderer = sysconfig.Renderer()
            renderer.render_network_state(render_dir, ns)
            for fn, expected_content in os_sample.get('out_sysconfig', []):
                with open(os.path.join(render_dir, fn)) as fh:
                    self.assertEqual(expected_content, fh.read())


class TestEniNetRendering(TestCase):

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.sys_netdev_info")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_sys_netdev_info,
                                mock_sys_dev_path):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir)
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_sys_netdev_info, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = eni.Renderer()
        renderer.render_network_state(render_dir, ns,
                                      eni="interfaces",
                                      links_prefix=None,
                                      netrules=None)

        self.assertTrue(os.path.exists(os.path.join(render_dir,
                                                    'interfaces')))
        with open(os.path.join(render_dir, 'interfaces')) as fh:
            contents = fh.read()

        expected = """
auto lo
iface lo inet loopback

auto eth1000
iface eth1000 inet dhcp
"""
        self.assertEqual(expected.lstrip(), contents.lstrip())


class TestCmdlineConfigParsing(TestCase):
    simple_cfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}]}

    def test_cmdline_convert_dhcp(self):
        found = cmdline._klibc_to_config_entry(DHCP_CONTENT_1)
        self.assertEqual(found, ('eth0', DHCP_EXPECTED_1))

    def test_cmdline_convert_static(self):
        found = cmdline._klibc_to_config_entry(STATIC_CONTENT_1)
        self.assertEqual(found, ('eth1', STATIC_EXPECTED_1))

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
        with util.tempdir() as tmpd:
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

    def test_cmdline_with_b64_gz(self):
        data = _gzip_data(json.dumps(self.simple_cfg).encode())
        encoded_text = base64.b64encode(data).decode()
        raw_cmdline = 'ro network-config=' + encoded_text + ' root=foo'
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        self.assertEqual(found, self.simple_cfg)


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()
