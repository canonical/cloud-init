from cloudinit import net
from cloudinit import util

from .helpers import TestCase

import base64
import copy
import gzip
import io
import json
import os
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

NETWORK_YAML_SMALL = """
version: 1
config:
    # Physical interfaces.
    - type: physical
      name: eth0
      mac_address: "c0:d6:9f:2c:e8:80"
      subnets:
          - type: dhcp4
          - type: static
            address: 192.168.21.3/24
            dns_nameservers:
              - 8.8.8.8
              - 8.8.4.4
            dns_search: barley.maas sach.maas
    - type: physical
      name: eth1
      mac_address: "cf:d6:af:48:e8:80"
    - type: nameserver
      address:
        - 1.2.3.4
        - 5.6.7.8
      search:
        - wark.maas
"""
NETWORK_YAML_ALL = """
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
"""


class TestNetConfigParsing(TestCase):
    simple_cfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}]}

    def test_klibc_convert_dhcp(self):
        found = net._klibc_to_config_entry(DHCP_CONTENT_1)
        self.assertEqual(found, ('eth0', DHCP_EXPECTED_1))

    def test_klibc_convert_static(self):
        found = net._klibc_to_config_entry(STATIC_CONTENT_1)
        self.assertEqual(found, ('eth1', STATIC_EXPECTED_1))

    def test_config_from_klibc_net_cfg(self):
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

            found = net.config_from_klibc_net_cfg(files=files, mac_addrs=macs)
            self.assertEqual(found, expected)

    def test_cmdline_with_b64(self):
        data = base64.b64encode(json.dumps(self.simple_cfg).encode())
        encoded_text = data.decode()
        cmdline = 'ro network-config=' + encoded_text + ' root=foo'
        found = net.read_kernel_cmdline_config(cmdline=cmdline)
        self.assertEqual(found, self.simple_cfg)

    def test_cmdline_with_b64_gz(self):
        data = _gzip_data(json.dumps(self.simple_cfg).encode())
        encoded_text = base64.b64encode(data).decode()
        cmdline = 'ro network-config=' + encoded_text + ' root=foo'
        found = net.read_kernel_cmdline_config(cmdline=cmdline)
        self.assertEqual(found, self.simple_cfg)


class TestEniRoundTrip(TestCase):
    def testsimple_convert_and_render(self):
        network_config = net.convert_eni_data(EXAMPLE_ENI)
        ns = net.parse_net_config_data(network_config)
        eni = net.render_interfaces(ns)
        print("Eni looks like:\n%s" % eni)
        raise Exception("FOO")

    def testsimple_render_all(self):
        network_config = yaml.load(NETWORK_YAML_ALL)
        ns = net.parse_net_config_data(network_config)
        eni = net.render_interfaces(ns)
        print("Eni looks like:\n%s" % eni)
        raise Exception("FOO")

    def testsimple_render_small(self):
        network_config = yaml.load(NETWORK_YAML_SMALL)
        ns = net.parse_net_config_data(network_config)
        eni = net.render_interfaces(ns)
        print("Eni looks like:\n%s" % eni)
        raise Exception("FOO")


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()
