# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import net
from cloudinit.net import cmdline
from cloudinit.net import eni
from cloudinit.net import network_state
from cloudinit.net import sysconfig
from cloudinit.sources.helpers import openstack
from cloudinit import util

from .helpers import dir2dict
from .helpers import mock
from .helpers import populate_dir
from .helpers import TempDirTestCase
from .helpers import TestCase

import base64
import copy
import gzip
import io
import json
import os
import shutil
import tempfile
import textwrap
import yaml

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

EXAMPLE_ENI = """
auto lo
iface lo inet loopback
   dns-nameservers 10.0.0.1
   dns-search foo.com

auto eth0
iface eth0 inet static
        address 1.2.3.12
        netmask 255.255.255.248
        broadcast 1.2.3.15
        gateway 1.2.3.9
        dns-nameservers 69.9.160.191 69.9.191.4
auto eth1
iface eth1 inet static
        address 10.248.2.4
        netmask 255.255.255.248
        broadcast 10.248.2.7
"""

RENDERED_ENI = """
auto lo
iface lo inet loopback
    dns-nameservers 10.0.0.1
    dns-search foo.com

auto eth0
iface eth0 inet static
    address 1.2.3.12
    broadcast 1.2.3.15
    dns-nameservers 69.9.160.191 69.9.191.4
    gateway 1.2.3.9
    netmask 255.255.255.248

auto eth1
iface eth1 inet static
    address 10.248.2.4
    broadcast 10.248.2.7
    netmask 255.255.255.248
""".lstrip()

NETWORK_CONFIGS = {
    'small': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback
                dns-nameservers 1.2.3.4 5.6.7.8
                dns-search wark.maas

            iface eth1 inet manual

            auto eth99
            iface eth99 inet dhcp
                post-up ifup eth99:1


            auto eth99:1
            iface eth99:1 inet static
                address 192.168.21.3/24
                dns-nameservers 8.8.8.8 8.8.4.4
                dns-search barley.maas sach.maas
                post-up route add default gw 65.61.151.37 || true
                pre-down route del default gw 65.61.151.37 || true
        """).rstrip(' '),
        'yaml': textwrap.dedent("""
            version: 1
            config:
                # Physical interfaces.
                - type: physical
                  name: eth99
                  mac_address: "c0:d6:9f:2c:e8:80"
                  subnets:
                      - type: dhcp4
                      - type: static
                        address: 192.168.21.3/24
                        dns_nameservers:
                          - 8.8.8.8
                          - 8.8.4.4
                        dns_search: barley.maas sach.maas
                        routes:
                          - gateway: 65.61.151.37
                            netmask: 0.0.0.0
                            network: 0.0.0.0
                            metric: 2
                - type: physical
                  name: eth1
                  mac_address: "cf:d6:af:48:e8:80"
                - type: nameserver
                  address:
                    - 1.2.3.4
                    - 5.6.7.8
                  search:
                    - wark.maas
        """),
    },
    'all': {
        'expected_eni': ("""\
auto lo
iface lo inet loopback
    dns-nameservers 8.8.8.8 4.4.4.4 8.8.4.4
    dns-search barley.maas wark.maas foobar.maas

iface eth0 inet manual

auto eth1
iface eth1 inet manual
    bond-master bond0
    bond-mode active-backup

auto eth2
iface eth2 inet manual
    bond-master bond0
    bond-mode active-backup

iface eth3 inet manual

iface eth4 inet manual

# control-manual eth5
iface eth5 inet dhcp

auto bond0
iface bond0 inet6 dhcp
    bond-mode active-backup
    bond-slaves none
    hwaddress aa:bb:cc:dd:ee:ff

auto br0
iface br0 inet static
    address 192.168.14.2/24
    bridge_ports eth3 eth4
    bridge_stp off
    post-up ifup br0:1


auto br0:1
iface br0:1 inet6 static
    address 2001:1::1/64

auto bond0.200
iface bond0.200 inet dhcp
    vlan-raw-device bond0
    vlan_id 200

auto eth0.101
iface eth0.101 inet static
    address 192.168.0.2/24
    dns-nameservers 192.168.0.10 10.23.23.134
    dns-search barley.maas sacchromyces.maas brettanomyces.maas
    gateway 192.168.0.1
    mtu 1500
    vlan-raw-device eth0
    vlan_id 101
    post-up ifup eth0.101:1


auto eth0.101:1
iface eth0.101:1 inet static
    address 192.168.2.10/24

post-up route add -net 10.0.0.0 netmask 255.0.0.0 gw 11.0.0.1 metric 3 || true
pre-down route del -net 10.0.0.0 netmask 255.0.0.0 gw 11.0.0.1 metric 3 || true
"""),
        'yaml': textwrap.dedent("""
            version: 1
            config:
                # Physical interfaces.
                - type: physical
                  name: eth0
                  mac_address: "c0:d6:9f:2c:e8:80"
                - type: physical
                  name: eth1
                  mac_address: "aa:d6:9f:2c:e8:80"
                - type: physical
                  name: eth2
                  mac_address: "c0:bb:9f:2c:e8:80"
                - type: physical
                  name: eth3
                  mac_address: "66:bb:9f:2c:e8:80"
                - type: physical
                  name: eth4
                  mac_address: "98:bb:9f:2c:e8:80"
                # specify how ifupdown should treat iface
                # control is one of ['auto', 'hotplug', 'manual']
                # with manual meaning ifup/ifdown should not affect the iface
                # useful for things like iscsi root + dhcp
                - type: physical
                  name: eth5
                  mac_address: "98:bb:9f:2c:e8:8a"
                  subnets:
                    - type: dhcp
                      control: manual
                # VLAN interface.
                - type: vlan
                  name: eth0.101
                  vlan_link: eth0
                  vlan_id: 101
                  mtu: 1500
                  subnets:
                    - type: static
                      address: 192.168.0.2/24
                      gateway: 192.168.0.1
                      dns_nameservers:
                        - 192.168.0.10
                        - 10.23.23.134
                      dns_search:
                        - barley.maas
                        - sacchromyces.maas
                        - brettanomyces.maas
                    - type: static
                      address: 192.168.2.10/24
                # Bond.
                - type: bond
                  name: bond0
                  # if 'mac_address' is omitted, the MAC is taken from
                  # the first slave.
                  mac_address: "aa:bb:cc:dd:ee:ff"
                  bond_interfaces:
                    - eth1
                    - eth2
                  params:
                    bond-mode: active-backup
                  subnets:
                    - type: dhcp6
                # A Bond VLAN.
                - type: vlan
                  name: bond0.200
                  vlan_link: bond0
                  vlan_id: 200
                  subnets:
                      - type: dhcp4
                # A bridge.
                - type: bridge
                  name: br0
                  bridge_interfaces:
                      - eth3
                      - eth4
                  ipv4_conf:
                      rp_filter: 1
                      proxy_arp: 0
                      forwarding: 1
                  ipv6_conf:
                      autoconf: 1
                      disable_ipv6: 1
                      use_tempaddr: 1
                      forwarding: 1
                      # basically anything in /proc/sys/net/ipv6/conf/.../
                  params:
                      bridge_stp: 'off'
                      bridge_fd: 0
                      bridge_maxwait: 0
                  subnets:
                      - type: static
                        address: 192.168.14.2/24
                      - type: static
                        address: 2001:1::1/64 # default to /64
                # A global nameserver.
                - type: nameserver
                  address: 8.8.8.8
                  search: barley.maas
                # global nameservers and search in list form
                - type: nameserver
                  address:
                    - 4.4.4.4
                    - 8.8.4.4
                  search:
                    - wark.maas
                    - foobar.maas
                # A global route.
                - type: route
                  destination: 10.0.0.0/8
                  gateway: 11.0.0.1
                  metric: 3
        """).lstrip(),
    }
}


def _setup_test(tmp_dir, mock_get_devicelist, mock_read_sys_net,
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

    def fake_read(devname, path, translate=None,
                  on_enoent=None, on_keyerror=None,
                  on_einval=None):
        return dev_characteristics[devname][path]

    mock_read_sys_net.side_effect = fake_read

    def sys_dev_path(devname, path=""):
        return tmp_dir + devname + "/" + path

    for dev in dev_characteristics:
        os.makedirs(os.path.join(tmp_dir, dev))
        with open(os.path.join(tmp_dir, dev, 'operstate'), 'w') as fh:
            fh.write("down")

    mock_sys_dev_path.side_effect = sys_dev_path


class TestSysConfigRendering(TestCase):

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir)
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

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
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir)
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = eni.Renderer(
            {'links_path_prefix': None,
             'eni_path': 'interfaces', 'netrules_path': None,
             })
        renderer.render_network_state(render_dir, ns)

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


class TestEniNetworkStateToEni(TestCase):
    mycfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}],
        'version': 1}
    my_mac = 'c0:d6:9f:2c:e8:80'

    def test_no_header(self):
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            render_hwaddress=True)
        self.assertIn(self.my_mac, rendered)
        self.assertIn("hwaddress", rendered)

    def test_with_header(self):
        header = "# hello world\n"
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            header=header, render_hwaddress=True)
        self.assertIn(header, rendered)
        self.assertIn(self.my_mac, rendered)

    def test_no_hwaddress(self):
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            render_hwaddress=False)
        self.assertNotIn(self.my_mac, rendered)
        self.assertNotIn("hwaddress", rendered)


class TestCmdlineConfigParsing(TestCase):
    simple_cfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}]}

    def test_cmdline_convert_dhcp(self):
        found = cmdline._klibc_to_config_entry(DHCP_CONTENT_1)
        self.assertEqual(found, ('eth0', DHCP_EXPECTED_1))

    def test_cmdline_convert_dhcp6(self):
        found = cmdline._klibc_to_config_entry(DHCP6_CONTENT_1)
        self.assertEqual(found, ('eno1', DHCP6_EXPECTED_1))

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


class TestCmdlineReadKernelConfig(TempDirTestCase):
    macs = {
        'eth0': '14:02:ec:42:48:00',
        'eno1': '14:02:ec:42:48:01',
    }

    def test_ip_cmdline_read_kernel_cmdline_ip(self):
        content = {'net-eth0.conf': DHCP_CONTENT_1}
        populate_dir(self.tmp, content)
        files = [os.path.join(self.tmp, k) for k in content.keys()]
        found = cmdline.read_kernel_cmdline_config(
            files=files, cmdline='foo ip=dhcp', mac_addrs=self.macs)
        exp1 = copy.deepcopy(DHCP_EXPECTED_1)
        exp1['mac_address'] = self.macs['eth0']
        self.assertEqual(found['version'], 1)
        self.assertEqual(found['config'], [exp1])

    def test_ip_cmdline_read_kernel_cmdline_ip6(self):
        content = {'net6-eno1.conf': DHCP6_CONTENT_1}
        populate_dir(self.tmp, content)
        files = [os.path.join(self.tmp, k) for k in content.keys()]
        found = cmdline.read_kernel_cmdline_config(
            files=files, cmdline='foo ip6=dhcp root=/dev/sda',
            mac_addrs=self.macs)
        self.assertEqual(
            found,
            {'version': 1, 'config': [
             {'type': 'physical', 'name': 'eno1',
              'mac_address': self.macs['eno1'],
              'subnets': [
                  {'dns_nameservers': ['2001:67c:1562:8010::2:1'],
                   'control': 'manual', 'type': 'dhcp6', 'netmask': '64'}]}]})

    def test_ip_cmdline_read_kernel_cmdline_none(self):
        # if there is no ip= or ip6= on cmdline, return value should be None
        content = {'net6-eno1.conf': DHCP6_CONTENT_1}
        populate_dir(self.tmp, content)
        files = [os.path.join(self.tmp, k) for k in content.keys()]
        found = cmdline.read_kernel_cmdline_config(
            files=files, cmdline='foo root=/dev/sda', mac_addrs=self.macs)
        self.assertEqual(found, None)

    def test_ip_cmdline_both_ip_ip6(self):
        content = {'net-eth0.conf': DHCP_CONTENT_1,
                   'net6-eth0.conf': DHCP6_CONTENT_1.replace('eno1', 'eth0')}
        populate_dir(self.tmp, content)
        files = [os.path.join(self.tmp, k) for k in sorted(content.keys())]
        found = cmdline.read_kernel_cmdline_config(
            files=files, cmdline='foo ip=dhcp ip6=dhcp', mac_addrs=self.macs)

        eth0 = copy.deepcopy(DHCP_EXPECTED_1)
        eth0['mac_address'] = self.macs['eth0']
        eth0['subnets'].append(
            {'control': 'manual', 'type': 'dhcp6',
             'netmask': '64', 'dns_nameservers': ['2001:67c:1562:8010::2:1']})
        expected = [eth0]
        self.assertEqual(found['version'], 1)
        self.assertEqual(found['config'], expected)


class TestEniRoundTrip(TestCase):
    def setUp(self):
        super(TestCase, self).setUp()
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir)

    def _render_and_read(self, network_config=None, state=None, eni_path=None,
                         links_prefix=None, netrules_path=None):
        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if eni_path is None:
            eni_path = 'etc/network/interfaces'

        renderer = eni.Renderer(
            config={'eni_path': eni_path, 'links_path_prefix': links_prefix,
                    'netrules_path': netrules_path})

        renderer.render_network_state(self.tmp_dir, ns)
        return dir2dict(self.tmp_dir)

    def testsimple_convert_and_render(self):
        network_config = eni.convert_eni_data(EXAMPLE_ENI)
        files = self._render_and_read(network_config=network_config)
        self.assertEqual(
            RENDERED_ENI.splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_all(self):
        entry = NETWORK_CONFIGS['all']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_small(self):
        entry = NETWORK_CONFIGS['small']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def test_routes_rendered(self):
        # as reported in bug 1649652
        conf = [
            {'name': 'eth0', 'type': 'physical',
             'subnets': [{
                 'address': '172.23.31.42/26',
                 'dns_nameservers': [], 'gateway': '172.23.31.2',
                 'type': 'static'}]},
            {'type': 'route', 'id': 4,
             'metric': 0, 'destination': '10.0.0.0/12',
             'gateway': '172.23.31.1'},
            {'type': 'route', 'id': 5,
             'metric': 0, 'destination': '192.168.2.0/16',
             'gateway': '172.23.31.1'},
            {'type': 'route', 'id': 6,
             'metric': 1, 'destination': '10.0.200.0/16',
             'gateway': '172.23.31.1'},
        ]

        files = self._render_and_read(
            network_config={'config': conf, 'version': 1})
        expected = [
            'auto lo',
            'iface lo inet loopback',
            'auto eth0',
            'iface eth0 inet static',
            '    address 172.23.31.42/26',
            '    gateway 172.23.31.2',
            ('post-up route add -net 10.0.0.0 netmask 255.240.0.0 gw '
             '172.23.31.1 metric 0 || true'),
            ('pre-down route del -net 10.0.0.0 netmask 255.240.0.0 gw '
             '172.23.31.1 metric 0 || true'),
            ('post-up route add -net 192.168.2.0 netmask 255.255.0.0 gw '
             '172.23.31.1 metric 0 || true'),
            ('pre-down route del -net 192.168.2.0 netmask 255.255.0.0 gw '
             '172.23.31.1 metric 0 || true'),
            ('post-up route add -net 10.0.200.0 netmask 255.255.0.0 gw '
             '172.23.31.1 metric 1 || true'),
            ('pre-down route del -net 10.0.200.0 netmask 255.255.0.0 gw '
             '172.23.31.1 metric 1 || true'),
        ]
        found = files['/etc/network/interfaces'].splitlines()

        self.assertEqual(
            expected, [line for line in found if line])


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()

# vi: ts=4 expandtab
