# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import net
from cloudinit import distros
from cloudinit.net import cmdline
from cloudinit.net import (
    eni, interface_has_own_mac, natural_sort_key, netplan, network_state,
    renderers, sysconfig)
from cloudinit.sources.helpers import openstack
from cloudinit import temp_utils
from cloudinit import util
from cloudinit import safeyaml as yaml

from cloudinit.tests.helpers import (
    CiTestCase, FilesystemMockingTestCase, dir2dict, mock, populate_dir)

import base64
import copy
import gzip
import io
import json
import os
import re
import textwrap
from yaml.serializer import Serializer


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

V1_NAMESERVER_ALIAS = """
config:
-   id: eno1
    mac_address: 08:94:ef:51:ae:e0
    mtu: 1500
    name: eno1
    subnets:
    -   type: manual
    type: physical
-   id: eno2
    mac_address: 08:94:ef:51:ae:e1
    mtu: 1500
    name: eno2
    subnets:
    -   type: manual
    type: physical
-   id: eno3
    mac_address: 08:94:ef:51:ae:de
    mtu: 1500
    name: eno3
    subnets:
    -   type: manual
    type: physical
-   bond_interfaces:
    - eno1
    - eno3
    id: bondM
    mac_address: 08:94:ef:51:ae:e0
    mtu: 1500
    name: bondM
    params:
        bond-downdelay: 0
        bond-lacp-rate: fast
        bond-miimon: 100
        bond-mode: 802.3ad
        bond-updelay: 0
        bond-xmit-hash-policy: layer3+4
    subnets:
    -   address: 10.101.10.47/23
        gateway: 10.101.11.254
        type: static
    type: bond
-   id: eno4
    mac_address: 08:94:ef:51:ae:df
    mtu: 1500
    name: eno4
    subnets:
    -   type: manual
    type: physical
-   id: enp0s20f0u1u6
    mac_address: 0a:94:ef:51:a4:b9
    mtu: 1500
    name: enp0s20f0u1u6
    subnets:
    -   type: manual
    type: physical
-   id: enp216s0f0
    mac_address: 68:05:ca:81:7c:e8
    mtu: 9000
    name: enp216s0f0
    subnets:
    -   type: manual
    type: physical
-   id: enp216s0f1
    mac_address: 68:05:ca:81:7c:e9
    mtu: 9000
    name: enp216s0f1
    subnets:
    -   type: manual
    type: physical
-   id: enp47s0f0
    mac_address: 68:05:ca:64:d3:6c
    mtu: 9000
    name: enp47s0f0
    subnets:
    -   type: manual
    type: physical
-   bond_interfaces:
    - enp216s0f0
    - enp47s0f0
    id: bond0
    mac_address: 68:05:ca:64:d3:6c
    mtu: 9000
    name: bond0
    params:
        bond-downdelay: 0
        bond-lacp-rate: fast
        bond-miimon: 100
        bond-mode: 802.3ad
        bond-updelay: 0
        bond-xmit-hash-policy: layer3+4
    subnets:
    -   type: manual
    type: bond
-   id: bond0.3502
    mtu: 9000
    name: bond0.3502
    subnets:
    -   address: 172.20.80.4/25
        type: static
    type: vlan
    vlan_id: 3502
    vlan_link: bond0
-   id: bond0.3503
    mtu: 9000
    name: bond0.3503
    subnets:
    -   address: 172.20.80.129/25
        type: static
    type: vlan
    vlan_id: 3503
    vlan_link: bond0
-   id: enp47s0f1
    mac_address: 68:05:ca:64:d3:6d
    mtu: 9000
    name: enp47s0f1
    subnets:
    -   type: manual
    type: physical
-   bond_interfaces:
    - enp216s0f1
    - enp47s0f1
    id: bond1
    mac_address: 68:05:ca:64:d3:6d
    mtu: 9000
    name: bond1
    params:
        bond-downdelay: 0
        bond-lacp-rate: fast
        bond-miimon: 100
        bond-mode: 802.3ad
        bond-updelay: 0
        bond-xmit-hash-policy: layer3+4
    subnets:
    -   address: 10.101.8.65/26
        routes:
        -   destination: 213.119.192.0/24
            gateway: 10.101.8.126
            metric: 0
        type: static
    type: bond
-   address:
    - 10.101.10.1
    - 10.101.10.2
    - 10.101.10.3
    - 10.101.10.5
    search:
    - foo.bar
    - maas
    type: nameserver
version: 1
"""

NETPLAN_NO_ALIAS = """
network:
    version: 2
    ethernets:
        eno1:
            match:
                macaddress: 08:94:ef:51:ae:e0
            mtu: 1500
            set-name: eno1
        eno2:
            match:
                macaddress: 08:94:ef:51:ae:e1
            mtu: 1500
            set-name: eno2
        eno3:
            match:
                macaddress: 08:94:ef:51:ae:de
            mtu: 1500
            set-name: eno3
        eno4:
            match:
                macaddress: 08:94:ef:51:ae:df
            mtu: 1500
            set-name: eno4
        enp0s20f0u1u6:
            match:
                macaddress: 0a:94:ef:51:a4:b9
            mtu: 1500
            set-name: enp0s20f0u1u6
        enp216s0f0:
            match:
                macaddress: 68:05:ca:81:7c:e8
            mtu: 9000
            set-name: enp216s0f0
        enp216s0f1:
            match:
                macaddress: 68:05:ca:81:7c:e9
            mtu: 9000
            set-name: enp216s0f1
        enp47s0f0:
            match:
                macaddress: 68:05:ca:64:d3:6c
            mtu: 9000
            set-name: enp47s0f0
        enp47s0f1:
            match:
                macaddress: 68:05:ca:64:d3:6d
            mtu: 9000
            set-name: enp47s0f1
    bonds:
        bond0:
            interfaces:
            - enp216s0f0
            - enp47s0f0
            macaddress: 68:05:ca:64:d3:6c
            mtu: 9000
            parameters:
                down-delay: 0
                lacp-rate: fast
                mii-monitor-interval: 100
                mode: 802.3ad
                transmit-hash-policy: layer3+4
                up-delay: 0
        bond1:
            addresses:
            - 10.101.8.65/26
            interfaces:
            - enp216s0f1
            - enp47s0f1
            macaddress: 68:05:ca:64:d3:6d
            mtu: 9000
            nameservers:
                addresses:
                - 10.101.10.1
                - 10.101.10.2
                - 10.101.10.3
                - 10.101.10.5
                search:
                - foo.bar
                - maas
            parameters:
                down-delay: 0
                lacp-rate: fast
                mii-monitor-interval: 100
                mode: 802.3ad
                transmit-hash-policy: layer3+4
                up-delay: 0
            routes:
            -   metric: 0
                to: 213.119.192.0/24
                via: 10.101.8.126
        bondM:
            addresses:
            - 10.101.10.47/23
            gateway4: 10.101.11.254
            interfaces:
            - eno1
            - eno3
            macaddress: 08:94:ef:51:ae:e0
            mtu: 1500
            nameservers:
                addresses:
                - 10.101.10.1
                - 10.101.10.2
                - 10.101.10.3
                - 10.101.10.5
                search:
                - foo.bar
                - maas
            parameters:
                down-delay: 0
                lacp-rate: fast
                mii-monitor-interval: 100
                mode: 802.3ad
                transmit-hash-policy: layer3+4
                up-delay: 0
    vlans:
        bond0.3502:
            addresses:
            - 172.20.80.4/25
            id: 3502
            link: bond0
            mtu: 9000
            nameservers:
                addresses:
                - 10.101.10.1
                - 10.101.10.2
                - 10.101.10.3
                - 10.101.10.5
                search:
                - foo.bar
                - maas
        bond0.3503:
            addresses:
            - 172.20.80.129/25
            id: 3503
            link: bond0
            mtu: 9000
            nameservers:
                addresses:
                - 10.101.10.1
                - 10.101.10.2
                - 10.101.10.3
                - 10.101.10.5
                search:
                - foo.bar
                - maas
"""

NETPLAN_BOND_GRAT_ARP = """
network:
    bonds:
        bond0:
            interfaces:
            - ens3
            macaddress: 68:05:ca:64:d3:6c
            mtu: 9000
            parameters:
                gratuitious-arp: 1
        bond1:
            interfaces:
            - ens4
            macaddress: 68:05:ca:64:d3:6d
            mtu: 9000
            parameters:
                gratuitous-arp: 2
    ethernets:
        ens3:
            dhcp4: false
            dhcp6: false
            match:
                macaddress: 52:54:00:ab:cd:ef
        ens4:
            dhcp4: false
            dhcp6: false
            match:
                macaddress: 52:54:00:11:22:ff
    version: 2
"""

NETPLAN_DHCP_FALSE = """
version: 2
ethernets:
  ens3:
    match:
      macaddress: 52:54:00:ab:cd:ef
    dhcp4: false
    dhcp6: false
    addresses:
      - 192.168.42.100/24
      - 2001:db8::100/32
    gateway4: 192.168.42.1
    gateway6: 2001:db8::1
    nameservers:
      search: [example.com]
      addresses: [192.168.42.53, 1.1.1.1]
"""

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
        'out_sysconfig_opensuse': [
            ('etc/sysconfig/network/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
STARTMODE=auto
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
""".lstrip()),
            ('etc/udev/rules.d/85-persistent-net-cloud-init.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))],
        'out_sysconfig_rhel': [
            ('etc/sysconfig/network-scripts/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
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
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
""".lstrip()),
            ('etc/udev/rules.d/70-persistent-net.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))]

    },
    {
        'in_data': {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [{
                "network_id": "public-ipv4",
                "type": "ipv4", "netmask": "255.255.252.0",
                "link": "tap1a81968a-79",
                "routes": [{
                    "netmask": "0.0.0.0",
                    "network": "0.0.0.0",
                    "gateway": "172.19.3.254",
                }],
                "ip_address": "172.19.1.34", "id": "network0"
            }, {
                "network_id": "private-ipv4",
                "type": "ipv4", "netmask": "255.255.255.0",
                "link": "tap1a81968a-79",
                "routes": [],
                "ip_address": "10.0.0.10", "id": "network1"
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
        'out_sysconfig_opensuse': [
            ('etc/sysconfig/network/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
IPADDR1=10.0.0.10
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
NETMASK1=255.255.255.0
STARTMODE=auto
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
""".lstrip()),
            ('etc/udev/rules.d/85-persistent-net-cloud-init.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))],
        'out_sysconfig_rhel': [
            ('etc/sysconfig/network-scripts/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
GATEWAY=172.19.3.254
HWADDR=fa:16:3e:ed:9a:59
IPADDR=172.19.1.34
IPADDR1=10.0.0.10
NETMASK=255.255.252.0
NETMASK1=255.255.255.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
""".lstrip()),
            ('etc/udev/rules.d/70-persistent-net.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))]

    },
    {
        'in_data': {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [{
                "network_id": "public-ipv4",
                "type": "ipv4", "netmask": "255.255.252.0",
                "link": "tap1a81968a-79",
                "routes": [{
                    "netmask": "0.0.0.0",
                    "network": "0.0.0.0",
                    "gateway": "172.19.3.254",
                }],
                "ip_address": "172.19.1.34", "id": "network0"
            }, {
                "network_id": "public-ipv6-a",
                "type": "ipv6", "netmask": "",
                "link": "tap1a81968a-79",
                "routes": [
                    {
                        "gateway": "2001:DB8::1",
                        "netmask": "::",
                        "network": "::"
                    }
                ],
                "ip_address": "2001:DB8::10", "id": "network1"
            }, {
                "network_id": "public-ipv6-b",
                "type": "ipv6", "netmask": "64",
                "link": "tap1a81968a-79",
                "routes": [
                ],
                "ip_address": "2001:DB9::10", "id": "network2"
            }, {
                "network_id": "public-ipv6-c",
                "type": "ipv6", "netmask": "64",
                "link": "tap1a81968a-79",
                "routes": [
                ],
                "ip_address": "2001:DB10::10", "id": "network3"
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
        'out_sysconfig_opensuse': [
            ('etc/sysconfig/network/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
IPADDR6=2001:DB8::10/64
IPADDR6_1=2001:DB9::10/64
IPADDR6_2=2001:DB10::10/64
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
STARTMODE=auto
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
""".lstrip()),
            ('etc/udev/rules.d/85-persistent-net-cloud-init.rules',
             "".join(['SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                      'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n']))],
        'out_sysconfig_rhel': [
            ('etc/sysconfig/network-scripts/ifcfg-eth0',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
GATEWAY=172.19.3.254
HWADDR=fa:16:3e:ed:9a:59
IPADDR=172.19.1.34
IPV6ADDR=2001:DB8::10/64
IPV6ADDR_SECONDARIES="2001:DB9::10/64 2001:DB10::10/64"
IPV6INIT=yes
IPV6_DEFAULTGW=2001:DB8::1
NETMASK=255.255.252.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()),
            ('etc/resolv.conf',
             """
; Created by cloud-init on instance boot automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip()),
            ('etc/NetworkManager/conf.d/99-cloud-init.conf',
             """
# Created by cloud-init on instance boot automatically, do not edit.
#
[main]
dns = none
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
    address 1.2.3.12/29
    broadcast 1.2.3.15
    dns-nameservers 69.9.160.191 69.9.191.4
    gateway 1.2.3.9

auto eth1
iface eth1 inet static
    address 10.248.2.4/29
    broadcast 10.248.2.7
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

            # control-alias eth99
            iface eth99 inet static
                address 192.168.21.3/24
                dns-nameservers 8.8.8.8 8.8.4.4
                dns-search barley.maas sach.maas
                post-up route add default gw 65.61.151.37 metric 10000 || true
                pre-down route del default gw 65.61.151.37 metric 10000 || true
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    eth1:
                        match:
                            macaddress: cf:d6:af:48:e8:80
                        set-name: eth1
                    eth99:
                        addresses:
                        - 192.168.21.3/24
                        dhcp4: true
                        match:
                            macaddress: c0:d6:9f:2c:e8:80
                        nameservers:
                            addresses:
                            - 8.8.8.8
                            - 8.8.4.4
                            search:
                            - barley.maas
                            - sach.maas
                        routes:
                        -   metric: 10000
                            to: 0.0.0.0/0
                            via: 65.61.151.37
                        set-name: eth99
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=cf:d6:af:48:e8:80
                STARTMODE=auto"""),
            'ifcfg-eth99': textwrap.dedent("""\
                BOOTPROTO=dhcp4
                LLADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                STARTMODE=auto"""),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=cf:d6:af:48:e8:80
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth99': textwrap.dedent("""\
                BOOTPROTO=dhcp
                DEFROUTE=yes
                DEVICE=eth99
                DHCLIENT_SET_DEFAULT_ROUTE=yes
                DNS1=8.8.8.8
                DNS2=8.8.4.4
                DOMAIN="barley.maas sach.maas"
                GATEWAY=65.61.151.37
                HWADDR=c0:d6:9f:2c:e8:80
                IPADDR=192.168.21.3
                NETMASK=255.255.255.0
                METRIC=10000
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
        },
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
                            metric: 10000
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
    'v4_and_v6': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet dhcp

            # control-alias iface0
            iface iface0 inet6 dhcp
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp4: true
                        dhcp6: true
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0':  textwrap.dedent("""\
                BOOTPROTO=dhcp
                DHCLIENT6_MODE=managed
                STARTMODE=auto""")
        },
        'yaml': textwrap.dedent("""\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp4'}
                - {'type': 'dhcp6'}
        """).rstrip(' '),
    },
    'v4_and_v6_static': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet static
                address 192.168.14.2/24
                mtu 9000

            # control-alias iface0
            iface iface0 inet6 static
                address 2001:1::1/64
                mtu 1500
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        addresses:
                        - 192.168.14.2/24
                        - 2001:1::1/64
                        ipv6-mtu: 1500
                        mtu: 9000
        """).rstrip(' '),
        'yaml': textwrap.dedent("""\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                mtu: 8999
                subnets:
                  - type: static
                    address: 192.168.14.2/24
                    mtu: 9000
                  - type: static
                    address: 2001:1::1/64
                    mtu: 1500
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                NETMASK=255.255.255.0
                STARTMODE=auto
                MTU=9000
                """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=iface0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                MTU=9000
                IPV6_MTU=1500
                """),
        },
    },
    'v6_and_v4': {
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0':  textwrap.dedent("""\
                BOOTPROTO=dhcp
                DHCLIENT6_MODE=managed
                STARTMODE=auto""")
        },
        'yaml': textwrap.dedent("""\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                  - type: dhcp6
                  - type: dhcp4
        """).rstrip(' '),
    },
    'dhcpv6_only': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp6: true
        """).rstrip(' '),
        'yaml': textwrap.dedent("""\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp6'}
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
                """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                DEVICE=iface0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
        },
    },
    'dhcpv6_accept_ra': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
                accept_ra 1
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        accept-ra: true
                        dhcp6: true
        """).rstrip(' '),
        'yaml_v1': textwrap.dedent("""\
            version: 1
            config:
              - type: 'physical'
                name: 'iface0'
                subnets:
                - {'type': 'dhcp6'}
                accept-ra: true
        """).rstrip(' '),
        'yaml_v2': textwrap.dedent("""\
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
                    accept-ra: true
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                IPV6_FORCE_ACCEPT_RA=yes
                DEVICE=iface0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """),
        },
    },
    'dhcpv6_reject_ra': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 dhcp
                accept_ra 0
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        accept-ra: false
                        dhcp6: true
        """).rstrip(' '),
        'yaml_v1': textwrap.dedent("""\
            version: 1
            config:
            - type: 'physical'
              name: 'iface0'
              subnets:
              - {'type': 'dhcp6'}
              accept-ra: false
        """).rstrip(' '),
        'yaml_v2': textwrap.dedent("""\
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
                    accept-ra: false
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                STARTMODE=auto
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=iface0
                DHCPV6C=yes
                IPV6INIT=yes
                IPV6_FORCE_ACCEPT_RA=no
                DEVICE=iface0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """),
        },
    },
    'ipv6_slaac': {
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto iface0
            iface iface0 inet6 auto
                dhcp 0
        """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    iface0:
                        dhcp6: true
        """).rstrip(' '),
        'yaml': textwrap.dedent("""\
            version: 1
            config:
            - type: 'physical'
              name: 'iface0'
              subnets:
              - {'type': 'ipv6_slaac'}
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=info
                STARTMODE=auto
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=iface0
                IPV6_AUTOCONF=yes
                IPV6INIT=yes
                DEVICE=iface0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
            """),
        },
    },
    'dhcpv6_stateless': {
        'expected_eni': textwrap.dedent("""\
        auto lo
        iface lo inet loopback

        auto iface0
        iface iface0 inet6 auto
            dhcp 1
    """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
        network:
            version: 2
            ethernets:
                iface0:
                    dhcp6: true
    """).rstrip(' '),
        'yaml': textwrap.dedent("""\
        version: 1
        config:
          - type: 'physical'
            name: 'iface0'
            subnets:
            - {'type': 'ipv6_dhcpv6-stateless'}
    """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
            BOOTPROTO=dhcp6
            DHCLIENT6_MODE=info
            STARTMODE=auto
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
            BOOTPROTO=none
            DEVICE=iface0
            DHCPV6C=yes
            DHCPV6C_OPTIONS=-S
            IPV6_AUTOCONF=yes
            IPV6INIT=yes
            DEVICE=iface0
            NM_CONTROLLED=no
            ONBOOT=yes
            TYPE=Ethernet
            USERCTL=no
            """),
        },
    },
    'dhcpv6_stateful': {
        'expected_eni': textwrap.dedent("""\
        auto lo
        iface lo inet loopback

        auto iface0
        iface iface0 inet6 dhcp
    """).rstrip(' '),
        'expected_netplan': textwrap.dedent("""
        network:
            version: 2
            ethernets:
                iface0:
                    accept-ra: true
                    dhcp6: true
    """).rstrip(' '),
        'yaml': textwrap.dedent("""\
        version: 1
        config:
          - type: 'physical'
            name: 'iface0'
            subnets:
            - {'type': 'ipv6_dhcpv6-stateful'}
            accept-ra: true
    """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-iface0': textwrap.dedent("""\
            BOOTPROTO=dhcp6
            DHCLIENT6_MODE=managed
            STARTMODE=auto
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-iface0': textwrap.dedent("""\
            BOOTPROTO=none
            DEVICE=iface0
            DHCPV6C=yes
            IPV6INIT=yes
            IPV6_FORCE_ACCEPT_RA=yes
            DEVICE=iface0
            NM_CONTROLLED=no
            ONBOOT=yes
            TYPE=Ethernet
            USERCTL=no
            """),
        },
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
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto eth2
iface eth2 inet manual
    bond-master bond0
    bond-mode active-backup
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

iface eth3 inet manual

iface eth4 inet manual

# control-manual eth5
iface eth5 inet dhcp

auto ib0
iface ib0 inet static
    address 192.168.200.7/24
    mtu 9000
    hwaddress a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1

auto bond0
iface bond0 inet6 dhcp
    bond-mode active-backup
    bond-slaves none
    bond-xmit-hash-policy layer3+4
    bond_miimon 100
    hwaddress aa:bb:cc:dd:ee:ff

auto br0
iface br0 inet static
    address 192.168.14.2/24
    bridge_ageing 250
    bridge_bridgeprio 22
    bridge_fd 1
    bridge_gcint 2
    bridge_hello 1
    bridge_maxage 10
    bridge_pathcost eth3 50
    bridge_pathcost eth4 75
    bridge_portprio eth3 28
    bridge_portprio eth4 14
    bridge_ports eth3 eth4
    bridge_stp off
    bridge_waitport 1 eth3
    bridge_waitport 2 eth4
    hwaddress bb:bb:bb:bb:bb:aa

# control-alias br0
iface br0 inet6 static
    address 2001:1::1/64
    post-up route add -A inet6 default gw 2001:4800:78ff:1b::1 || true
    pre-down route del -A inet6 default gw 2001:4800:78ff:1b::1 || true

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
    hwaddress aa:bb:cc:dd:ee:11
    vlan-raw-device eth0
    vlan_id 101

# control-alias eth0.101
iface eth0.101 inet static
    address 192.168.2.10/24

post-up route add -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
pre-down route del -net 10.0.0.0/8 gw 11.0.0.1 metric 3 || true
"""),
        'expected_netplan': textwrap.dedent("""
            network:
                version: 2
                ethernets:
                    eth0:
                        match:
                            macaddress: c0:d6:9f:2c:e8:80
                        set-name: eth0
                    eth1:
                        match:
                            macaddress: aa:d6:9f:2c:e8:80
                        set-name: eth1
                    eth2:
                        match:
                            macaddress: c0:bb:9f:2c:e8:80
                        set-name: eth2
                    eth3:
                        match:
                            macaddress: 66:bb:9f:2c:e8:80
                        set-name: eth3
                    eth4:
                        match:
                            macaddress: 98:bb:9f:2c:e8:80
                        set-name: eth4
                    eth5:
                        dhcp4: true
                        match:
                            macaddress: 98:bb:9f:2c:e8:8a
                        set-name: eth5
                bonds:
                    bond0:
                        dhcp6: true
                        interfaces:
                        - eth1
                        - eth2
                        macaddress: aa:bb:cc:dd:ee:ff
                        parameters:
                            mii-monitor-interval: 100
                            mode: active-backup
                            transmit-hash-policy: layer3+4
                bridges:
                    br0:
                        addresses:
                        - 192.168.14.2/24
                        - 2001:1::1/64
                        interfaces:
                        - eth3
                        - eth4
                        macaddress: bb:bb:bb:bb:bb:aa
                        nameservers:
                            addresses:
                            - 8.8.8.8
                            - 4.4.4.4
                            - 8.8.4.4
                            search:
                            - barley.maas
                            - wark.maas
                            - foobar.maas
                        parameters:
                            ageing-time: 250
                            forward-delay: 1
                            hello-time: 1
                            max-age: 10
                            path-cost:
                                eth3: 50
                                eth4: 75
                            port-priority:
                                eth3: 28
                                eth4: 14
                            priority: 22
                            stp: false
                        routes:
                        -   to: ::/0
                            via: 2001:4800:78ff:1b::1
                vlans:
                    bond0.200:
                        dhcp4: true
                        id: 200
                        link: bond0
                    eth0.101:
                        addresses:
                        - 192.168.0.2/24
                        - 192.168.2.10/24
                        gateway4: 192.168.0.1
                        id: 101
                        link: eth0
                        macaddress: aa:bb:cc:dd:ee:11
                        mtu: 1500
                        nameservers:
                            addresses:
                            - 192.168.0.10
                            - 10.23.23.134
                            search:
                            - barley.maas
                            - sacchromyces.maas
                            - brettanomyces.maas
        """).rstrip(' '),
        'expected_sysconfig_opensuse': {
            'ifcfg-bond0': textwrap.dedent("""\
                BONDING_MASTER=yes
                BONDING_OPTS="mode=active-backup """
                                           """xmit_hash_policy=layer3+4 """
                                           """miimon=100"
                BONDING_SLAVE_0=eth1
                BONDING_SLAVE_1=eth2
                BOOTPROTO=dhcp6
                DHCLIENT6_MODE=managed
                LLADDR=aa:bb:cc:dd:ee:ff
                STARTMODE=auto"""),
            'ifcfg-bond0.200': textwrap.dedent("""\
                BOOTPROTO=dhcp4
                ETHERDEVICE=bond0
                STARTMODE=auto
                VLAN_ID=200"""),
            'ifcfg-br0': textwrap.dedent("""\
                BRIDGE_AGEINGTIME=250
                BOOTPROTO=static
                IPADDR=192.168.14.2
                IPADDR6=2001:1::1/64
                LLADDRESS=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                BRIDGE_PRIORITY=22
                BRIDGE_PORTS='eth3 eth4'
                STARTMODE=auto
                BRIDGE_STP=off"""),
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=c0:d6:9f:2c:e8:80
                STARTMODE=auto"""),
            'ifcfg-eth0.101': textwrap.dedent("""\
                BOOTPROTO=static
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                ETHERDEVICE=eth0
                STARTMODE=auto
                VLAN_ID=101"""),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=none
                LLADDR=aa:d6:9f:2c:e8:80
                STARTMODE=hotplug"""),
            'ifcfg-eth2': textwrap.dedent("""\
                BOOTPROTO=none
                LLADDR=c0:bb:9f:2c:e8:80
                STARTMODE=hotplug"""),
            'ifcfg-eth3': textwrap.dedent("""\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=66:bb:9f:2c:e8:80
                STARTMODE=auto"""),
            'ifcfg-eth4': textwrap.dedent("""\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=98:bb:9f:2c:e8:80
                STARTMODE=auto"""),
            'ifcfg-eth5': textwrap.dedent("""\
                BOOTPROTO=dhcp
                LLADDR=98:bb:9f:2c:e8:8a
                STARTMODE=manual"""),
            'ifcfg-ib0': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                STARTMODE=auto
                TYPE=InfiniBand"""),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-bond0': textwrap.dedent("""\
                BONDING_MASTER=yes
                BONDING_OPTS="mode=active-backup """
                                           """xmit_hash_policy=layer3+4 """
                                           """miimon=100"
                BONDING_SLAVE0=eth1
                BONDING_SLAVE1=eth2
                BOOTPROTO=none
                DEVICE=bond0
                DHCPV6C=yes
                IPV6INIT=yes
                MACADDR=aa:bb:cc:dd:ee:ff
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Bond
                USERCTL=no"""),
            'ifcfg-bond0.200': textwrap.dedent("""\
                BOOTPROTO=dhcp
                DEVICE=bond0.200
                DHCLIENT_SET_DEFAULT_ROUTE=no
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=bond0
                TYPE=Ethernet
                USERCTL=no
                VLAN=yes"""),
            'ifcfg-br0': textwrap.dedent("""\
                AGEING=250
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=br0
                IPADDR=192.168.14.2
                IPV6ADDR=2001:1::1/64
                IPV6INIT=yes
                IPV6_DEFAULTGW=2001:4800:78ff:1b::1
                MACADDR=bb:bb:bb:bb:bb:aa
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PRIO=22
                STP=no
                TYPE=Bridge
                USERCTL=no"""),
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=c0:d6:9f:2c:e8:80
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth0.101': textwrap.dedent("""\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0.101
                DNS1=192.168.0.10
                DNS2=10.23.23.134
                DOMAIN="barley.maas sacchromyces.maas brettanomyces.maas"
                GATEWAY=192.168.0.1
                IPADDR=192.168.0.2
                IPADDR1=192.168.2.10
                MTU=1500
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=eth0
                TYPE=Ethernet
                USERCTL=no
                VLAN=yes"""),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=aa:d6:9f:2c:e8:80
                MASTER=bond0
                NM_CONTROLLED=no
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth2': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth2
                HWADDR=c0:bb:9f:2c:e8:80
                MASTER=bond0
                NM_CONTROLLED=no
                ONBOOT=yes
                SLAVE=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth3': textwrap.dedent("""\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth3
                HWADDR=66:bb:9f:2c:e8:80
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth4': textwrap.dedent("""\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth4
                HWADDR=98:bb:9f:2c:e8:80
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-eth5': textwrap.dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eth5
                DHCLIENT_SET_DEFAULT_ROUTE=no
                HWADDR=98:bb:9f:2c:e8:8a
                NM_CONTROLLED=no
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-ib0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=ib0
                HWADDR=a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                IPADDR=192.168.200.7
                MTU=9000
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=InfiniBand
                USERCTL=no"""),
        },
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
                  mac_address: aa:bb:cc:dd:ee:11
                  mtu: 1500
                  subnets:
                    - type: static
                      # When 'mtu' matches device-level mtu, no warnings
                      mtu: 1500
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
                    bond_miimon: 100
                    bond-xmit-hash-policy: "layer3+4"
                  subnets:
                    - type: dhcp6
                # A Bond VLAN.
                - type: vlan
                  name: bond0.200
                  vlan_link: bond0
                  vlan_id: 200
                  subnets:
                      - type: dhcp4
                # An infiniband
                - type: infiniband
                  name: ib0
                  mac_address: >-
                    a0:00:02:20:fe:80:00:00:00:00:00:00:ec:0d:9a:03:00:15:e2:c1
                  subnets:
                      - type: static
                        address: 192.168.200.7/24
                        mtu: 9000
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
                  mac_address: bb:bb:bb:bb:bb:aa
                  params:
                      bridge_ageing: 250
                      bridge_bridgeprio: 22
                      bridge_fd: 1
                      bridge_gcint: 2
                      bridge_hello: 1
                      bridge_maxage: 10
                      bridge_maxwait: 0
                      bridge_pathcost:
                        - eth3 50
                        - eth4 75
                      bridge_portprio:
                        - eth3 28
                        - eth4 14
                      bridge_stp: 'off'
                      bridge_waitport:
                        - 1 eth3
                        - 2 eth4
                  subnets:
                      - type: static
                        address: 192.168.14.2/24
                      - type: static
                        address: 2001:1::1/64 # default to /64
                        routes:
                          - gateway: 2001:4800:78ff:1b::1
                            netmask: '::'
                            network: '::'
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
    },
    'bond': {
        'yaml': textwrap.dedent("""
            version: 1
            config:
              - type: physical
                name: bond0s0
                mac_address: "aa:bb:cc:dd:e8:00"
              - type: physical
                name: bond0s1
                mac_address: "aa:bb:cc:dd:e8:01"
              - type: bond
                name: bond0
                mac_address: "aa:bb:cc:dd:e8:ff"
                mtu: 9000
                bond_interfaces:
                  - bond0s0
                  - bond0s1
                params:
                  bond-mode: active-backup
                  bond_miimon: 100
                  bond-xmit-hash-policy: "layer3+4"
                  bond-num-grat-arp: 5
                  bond-downdelay: 10
                  bond-updelay: 20
                  bond-fail-over-mac: active
                  bond-primary: bond0s0
                  bond-primary-reselect: always
                subnets:
                  - type: static
                    address: 192.168.0.2/24
                    gateway: 192.168.0.1
                    routes:
                     - gateway: 192.168.0.3
                       netmask: 255.255.255.0
                       network: 10.1.3.0
                  - type: static
                    address: 192.168.1.2/24
                  - type: static
                    address: 2001:1::1/92
                    routes:
                        - gateway: 2001:67c:1562:1
                          network: 2001:67c:1
                          netmask: ffff:ffff:0
                        - gateway: 3001:67c:1562:1
                          network: 3001:67c:1
                          netmask: ffff:ffff:0
                          metric: 10000
            """),
        'expected_netplan': textwrap.dedent("""
         network:
             version: 2
             ethernets:
                 bond0s0:
                     match:
                         macaddress: aa:bb:cc:dd:e8:00
                     set-name: bond0s0
                 bond0s1:
                     match:
                         macaddress: aa:bb:cc:dd:e8:01
                     set-name: bond0s1
             bonds:
                 bond0:
                     addresses:
                     - 192.168.0.2/24
                     - 192.168.1.2/24
                     - 2001:1::1/92
                     gateway4: 192.168.0.1
                     interfaces:
                     - bond0s0
                     - bond0s1
                     macaddress: aa:bb:cc:dd:e8:ff
                     mtu: 9000
                     parameters:
                         down-delay: 10
                         fail-over-mac-policy: active
                         gratuitious-arp: 5
                         mii-monitor-interval: 100
                         mode: active-backup
                         primary: bond0s0
                         primary-reselect-policy: always
                         transmit-hash-policy: layer3+4
                         up-delay: 20
                     routes:
                     -   to: 10.1.3.0/24
                         via: 192.168.0.3
                     -   to: 2001:67c:1/32
                         via: 2001:67c:1562:1
                     -   metric: 10000
                         to: 3001:67c:1/32
                         via: 3001:67c:1562:1
        """),
        'expected_eni': textwrap.dedent("""\
auto lo
iface lo inet loopback

auto bond0s0
iface bond0s0 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto bond0s1
iface bond0s1 inet manual
    bond-downdelay 10
    bond-fail-over-mac active
    bond-master bond0
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100

auto bond0
iface bond0 inet static
    address 192.168.0.2/24
    gateway 192.168.0.1
    bond-downdelay 10
    bond-fail-over-mac active
    bond-mode active-backup
    bond-num-grat-arp 5
    bond-primary bond0s0
    bond-primary-reselect always
    bond-slaves none
    bond-updelay 20
    bond-xmit-hash-policy layer3+4
    bond_miimon 100
    hwaddress aa:bb:cc:dd:e8:ff
    mtu 9000
    post-up route add -net 10.1.3.0/24 gw 192.168.0.3 || true
    pre-down route del -net 10.1.3.0/24 gw 192.168.0.3 || true

# control-alias bond0
iface bond0 inet static
    address 192.168.1.2/24

# control-alias bond0
iface bond0 inet6 static
    address 2001:1::1/92
    post-up route add -A inet6 2001:67c:1/32 gw 2001:67c:1562:1 || true
    pre-down route del -A inet6 2001:67c:1/32 gw 2001:67c:1562:1 || true
    post-up route add -A inet6 3001:67c:1/32 gw 3001:67c:1562:1 metric 10000 \
|| true
    pre-down route del -A inet6 3001:67c:1/32 gw 3001:67c:1562:1 metric 10000 \
|| true
        """),
        'yaml-v2': textwrap.dedent("""
            version: 2
            ethernets:
              eth0:
                match:
                    driver: "virtio_net"
                    macaddress: "aa:bb:cc:dd:e8:00"
              vf0:
                set-name: vf0
                match:
                    driver: "e1000"
                    macaddress: "aa:bb:cc:dd:e8:01"
            bonds:
              bond0:
                addresses:
                - 192.168.0.2/24
                - 192.168.1.2/24
                - 2001:1::1/92
                gateway4: 192.168.0.1
                interfaces:
                - eth0
                - vf0
                parameters:
                    down-delay: 10
                    fail-over-mac-policy: active
                    gratuitious-arp: 5
                    mii-monitor-interval: 100
                    mode: active-backup
                    primary: bond0s0
                    primary-reselect-policy: always
                    transmit-hash-policy: layer3+4
                    up-delay: 20
                routes:
                -   to: 10.1.3.0/24
                    via: 192.168.0.3
                -   to: 2001:67c:1562:8007::1/64
                    via: 2001:67c:1562:8007::aac:40b2
                -   metric: 10000
                    to: 3001:67c:1562:8007::1/64
                    via: 3001:67c:1562:8007::aac:40b2
            """),
        'expected_netplan-v2': textwrap.dedent("""
         network:
             bonds:
                 bond0:
                     addresses:
                     - 192.168.0.2/24
                     - 192.168.1.2/24
                     - 2001:1::1/92
                     gateway4: 192.168.0.1
                     interfaces:
                     - eth0
                     - vf0
                     parameters:
                         down-delay: 10
                         fail-over-mac-policy: active
                         gratuitious-arp: 5
                         mii-monitor-interval: 100
                         mode: active-backup
                         primary: bond0s0
                         primary-reselect-policy: always
                         transmit-hash-policy: layer3+4
                         up-delay: 20
                     routes:
                     -   to: 10.1.3.0/24
                         via: 192.168.0.3
                     -   to: 2001:67c:1562:8007::1/64
                         via: 2001:67c:1562:8007::aac:40b2
                     -   metric: 10000
                         to: 3001:67c:1562:8007::1/64
                         via: 3001:67c:1562:8007::aac:40b2
             ethernets:
                 eth0:
                     match:
                         driver: virtio_net
                         macaddress: aa:bb:cc:dd:e8:00
                 vf0:
                     match:
                         driver: e1000
                         macaddress: aa:bb:cc:dd:e8:01
                     set-name: vf0
             version: 2
        """),

        'expected_sysconfig_opensuse': {
            'ifcfg-bond0': textwrap.dedent("""\
        BONDING_MASTER=yes
        BONDING_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                                           """miimon=100 num_grat_arp=5 """
                                           """downdelay=10 updelay=20 """
                                           """fail_over_mac=active """
                                           """primary=bond0s0 """
                                           """primary_reselect=always"
        BONDING_SLAVE_0=bond0s0
        BONDING_SLAVE_1=bond0s1
        BOOTPROTO=static
        LLADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPADDR6=2001:1::1/92
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        STARTMODE=auto
        """),
            'ifcfg-bond0s0': textwrap.dedent("""\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:00
        STARTMODE=hotplug
        """),
            'ifcfg-bond0s1': textwrap.dedent("""\
        BOOTPROTO=none
        LLADDR=aa:bb:cc:dd:e8:01
        STARTMODE=hotplug
        """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-bond0': textwrap.dedent("""\
        BONDING_MASTER=yes
        BONDING_OPTS="mode=active-backup xmit_hash_policy=layer3+4 """
                                           """miimon=100 num_grat_arp=5 """
                                           """downdelay=10 updelay=20 """
                                           """fail_over_mac=active """
                                           """primary=bond0s0 """
                                           """primary_reselect=always"
        BONDING_SLAVE0=bond0s0
        BONDING_SLAVE1=bond0s1
        BOOTPROTO=none
        DEFROUTE=yes
        DEVICE=bond0
        GATEWAY=192.168.0.1
        MACADDR=aa:bb:cc:dd:e8:ff
        IPADDR=192.168.0.2
        IPADDR1=192.168.1.2
        IPV6ADDR=2001:1::1/92
        IPV6INIT=yes
        MTU=9000
        NETMASK=255.255.255.0
        NETMASK1=255.255.255.0
        NM_CONTROLLED=no
        ONBOOT=yes
        TYPE=Bond
        USERCTL=no
        """),
            'ifcfg-bond0s0': textwrap.dedent("""\
        BOOTPROTO=none
        DEVICE=bond0s0
        HWADDR=aa:bb:cc:dd:e8:00
        MASTER=bond0
        NM_CONTROLLED=no
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """),
            'route6-bond0': textwrap.dedent("""\
        # Created by cloud-init on instance boot automatically, do not edit.
        #
        2001:67c:1/ffff:ffff:0 via 2001:67c:1562:1  dev bond0
        3001:67c:1/ffff:ffff:0 via 3001:67c:1562:1 metric 10000 dev bond0
            """),
            'route-bond0': textwrap.dedent("""\
        ADDRESS0=10.1.3.0
        GATEWAY0=192.168.0.3
        NETMASK0=255.255.255.0
        """),
            'ifcfg-bond0s1': textwrap.dedent("""\
        BOOTPROTO=none
        DEVICE=bond0s1
        HWADDR=aa:bb:cc:dd:e8:01
        MASTER=bond0
        NM_CONTROLLED=no
        ONBOOT=yes
        SLAVE=yes
        TYPE=Ethernet
        USERCTL=no
        """),
        },
    },
    'vlan': {
        'yaml': textwrap.dedent("""
            version: 1
            config:
              - type: physical
                name: en0
                mac_address: "aa:bb:cc:dd:e8:00"
              - type: vlan
                mtu: 2222
                name: en0.99
                vlan_link: en0
                vlan_id: 99
                subnets:
                  - type: static
                    address: '192.168.2.2/24'
                  - type: static
                    address: '192.168.1.2/24'
                    gateway: 192.168.1.1
                  - type: static
                    address: 2001:1::bbbb/96
                    routes:
                     - gateway: 2001:1::1
                       netmask: '::'
                       network: '::'
            """),
        'expected_sysconfig_opensuse': {
            # TODO RJS: unknown proper BOOTPROTO setting ask Marius
            'ifcfg-en0': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=aa:bb:cc:dd:e8:00
                STARTMODE=auto"""),
            'ifcfg-en0.99': textwrap.dedent("""\
                BOOTPROTO=static
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPADDR6=2001:1::bbbb/96
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                STARTMODE=auto
                ETHERDEVICE=en0
                VLAN_ID=99
            """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-en0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=en0
                HWADDR=aa:bb:cc:dd:e8:00
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no"""),
            'ifcfg-en0.99': textwrap.dedent("""\
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=en0.99
                GATEWAY=192.168.1.1
                IPADDR=192.168.2.2
                IPADDR1=192.168.1.2
                IPV6ADDR=2001:1::bbbb/96
                IPV6INIT=yes
                IPV6_DEFAULTGW=2001:1::1
                MTU=2222
                NETMASK=255.255.255.0
                NETMASK1=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=en0
                TYPE=Ethernet
                USERCTL=no
                VLAN=yes"""),
        },
    },
    'bridge': {
        'yaml': textwrap.dedent("""
            version: 1
            config:
              - type: physical
                name: eth0
                mac_address: "52:54:00:12:34:00"
                subnets:
                  - type: static
                    address: 2001:1::100/96
              - type: physical
                name: eth1
                mac_address: "52:54:00:12:34:01"
                subnets:
                  - type: static
                    address: 2001:1::101/96
              - type: bridge
                name: br0
                bridge_interfaces:
                  - eth0
                  - eth1
                params:
                  bridge_stp: 0
                  bridge_bridgeprio: 22
                subnets:
                  - type: static
                    address: 192.168.2.2/24"""),
        'expected_sysconfig_opensuse': {
            'ifcfg-br0': textwrap.dedent("""\
                BOOTPROTO=static
                IPADDR=192.168.2.2
                NETMASK=255.255.255.0
                STARTMODE=auto
                BRIDGE_STP=off
                BRIDGE_PRIORITY=22
                BRIDGE_PORTS='eth0 eth1'
                """),
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=52:54:00:12:34:00
                IPADDR6=2001:1::100/96
                STARTMODE=auto
                """),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=static
                BRIDGE=yes
                LLADDR=52:54:00:12:34:01
                IPADDR6=2001:1::101/96
                STARTMODE=auto
                """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-br0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=br0
                IPADDR=192.168.2.2
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PRIO=22
                STP=no
                TYPE=Bridge
                USERCTL=no
                """),
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth0
                HWADDR=52:54:00:12:34:00
                IPV6ADDR=2001:1::100/96
                IPV6INIT=yes
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=none
                BRIDGE=br0
                DEVICE=eth1
                HWADDR=52:54:00:12:34:01
                IPV6ADDR=2001:1::101/96
                IPV6INIT=yes
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
        },
    },
    'manual': {
        'yaml': textwrap.dedent("""
            version: 1
            config:
              - type: physical
                name: eth0
                mac_address: "52:54:00:12:34:00"
                subnets:
                  - type: static
                    address: 192.168.1.2/24
                    control: manual
              - type: physical
                name: eth1
                mtu: 1480
                mac_address: "52:54:00:12:34:aa"
                subnets:
                  - type: manual
              - type: physical
                name: eth2
                mac_address: "52:54:00:12:34:ff"
                subnets:
                  - type: manual
                    control: manual
                  """),
        'expected_eni': textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            # control-manual eth0
            iface eth0 inet static
                address 192.168.1.2/24

            auto eth1
            iface eth1 inet manual
                mtu 1480

            # control-manual eth2
            iface eth2 inet manual
            """),
        'expected_netplan': textwrap.dedent("""\

            network:
                version: 2
                ethernets:
                    eth0:
                        addresses:
                        - 192.168.1.2/24
                        match:
                            macaddress: '52:54:00:12:34:00'
                        set-name: eth0
                    eth1:
                        match:
                            macaddress: 52:54:00:12:34:aa
                        mtu: 1480
                        set-name: eth1
                    eth2:
                        match:
                            macaddress: 52:54:00:12:34:ff
                        set-name: eth2
            """),
        'expected_sysconfig_opensuse': {
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:00
                IPADDR=192.168.1.2
                NETMASK=255.255.255.0
                STARTMODE=manual
                """),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:aa
                MTU=1480
                STARTMODE=auto
                """),
            'ifcfg-eth2': textwrap.dedent("""\
                BOOTPROTO=static
                LLADDR=52:54:00:12:34:ff
                STARTMODE=manual
                """),
        },
        'expected_sysconfig_rhel': {
            'ifcfg-eth0': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth0
                HWADDR=52:54:00:12:34:00
                IPADDR=192.168.1.2
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no
                """),
            'ifcfg-eth1': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth1
                HWADDR=52:54:00:12:34:aa
                MTU=1480
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            'ifcfg-eth2': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eth2
                HWADDR=52:54:00:12:34:ff
                NM_CONTROLLED=no
                ONBOOT=no
                TYPE=Ethernet
                USERCTL=no
                """),
        },
    },
}


CONFIG_V1_EXPLICIT_LOOPBACK = {
    'version': 1,
    'config': [{'name': 'eth0', 'type': 'physical',
               'subnets': [{'control': 'auto', 'type': 'dhcp'}]},
               {'name': 'lo', 'type': 'loopback',
                'subnets': [{'control': 'auto', 'type': 'loopback'}]},
               ]}


CONFIG_V1_SIMPLE_SUBNET = {
    'version': 1,
    'config': [{'mac_address': '52:54:00:12:34:00',
                'name': 'interface0',
                'subnets': [{'address': '10.0.2.15',
                             'gateway': '10.0.2.2',
                             'netmask': '255.255.255.0',
                             'type': 'static'}],
                'type': 'physical'}]}

CONFIG_V1_MULTI_IFACE = {
    'version': 1,
    'config': [{'type': 'physical',
                'mtu': 1500,
                'subnets': [{'type': 'static',
                             'netmask': '255.255.240.0',
                             'routes': [{'netmask': '0.0.0.0',
                                         'network': '0.0.0.0',
                                         'gateway': '51.68.80.1'}],
                             'address': '51.68.89.122',
                             'ipv4': True}],
                'mac_address': 'fa:16:3e:25:b4:59',
                'name': 'eth0'},
               {'type': 'physical',
                'mtu': 9000,
                'subnets': [{'type': 'dhcp4'}],
                'mac_address': 'fa:16:3e:b1:ca:29', 'name': 'eth1'}]}

DEFAULT_DEV_ATTRS = {
    'eth1000': {
        "bridge": False,
        "carrier": False,
        "dormant": False,
        "operstate": "down",
        "address": "07-1c-c6-75-a4-be",
        "device/driver": None,
        "device/device": None,
        "name_assign_type": "4",
    }
}


def _setup_test(tmp_dir, mock_get_devicelist, mock_read_sys_net,
                mock_sys_dev_path, dev_attrs=None):
    if not dev_attrs:
        dev_attrs = DEFAULT_DEV_ATTRS

    mock_get_devicelist.return_value = dev_attrs.keys()

    def fake_read(devname, path, translate=None,
                  on_enoent=None, on_keyerror=None,
                  on_einval=None):
        return dev_attrs[devname][path]

    mock_read_sys_net.side_effect = fake_read

    def sys_dev_path(devname, path=""):
        return tmp_dir + "/" + devname + "/" + path

    for dev in dev_attrs:
        os.makedirs(os.path.join(tmp_dir, dev))
        with open(os.path.join(tmp_dir, dev, 'operstate'), 'w') as fh:
            fh.write(dev_attrs[dev]['operstate'])
        os.makedirs(os.path.join(tmp_dir, dev, "device"))
        for key in ['device/driver']:
            if key in dev_attrs[dev] and dev_attrs[dev][key]:
                target = dev_attrs[dev][key]
                link = os.path.join(tmp_dir, dev, key)
                print('symlink %s -> %s' % (link, target))
                os.symlink(target, link)

    mock_sys_dev_path.side_effect = sys_dev_path


class TestGenerateFallbackConfig(CiTestCase):

    def setUp(self):
        super(TestGenerateFallbackConfig, self).setUp()
        self.add_patch(
            "cloudinit.util.get_cmdline", "m_get_cmdline",
            return_value="root=/dev/sda1")

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_device_driver_v2(self, mock_get_devicelist, mock_read_sys_net,
                              mock_sys_dev_path):
        """Network configuration for generate_fallback_config is version 2."""
        devices = {
            'eth0': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'hv_netsvc', 'device/device': '0x3',
                'name_assign_type': '4'},
            'eth1': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'mlx4_core', 'device/device': '0x7',
                'name_assign_type': '4'},

        }

        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path,
                    dev_attrs=devices)

        network_cfg = net.generate_fallback_config(config_driver=True)
        expected = {
            'ethernets': {'eth0': {'dhcp4': True, 'set-name': 'eth0',
                                   'match': {'macaddress': '00:11:22:33:44:55',
                                             'driver': 'hv_netsvc'}}},
            'version': 2}
        self.assertEqual(expected, network_cfg)

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_device_driver(self, mock_get_devicelist, mock_read_sys_net,
                           mock_sys_dev_path):
        devices = {
            'eth0': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'hv_netsvc', 'device/device': '0x3',
                'name_assign_type': '4'},
            'eth1': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'mlx4_core', 'device/device': '0x7',
                'name_assign_type': '4'},

        }

        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path,
                    dev_attrs=devices)

        network_cfg = net.generate_fallback_config(config_driver=True)
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        # don't set rulepath so eni writes them
        renderer = eni.Renderer(
            {'eni_path': 'interfaces', 'netrules_path': 'netrules'})
        renderer.render_network_state(ns, target=render_dir)

        self.assertTrue(os.path.exists(os.path.join(render_dir,
                                                    'interfaces')))
        with open(os.path.join(render_dir, 'interfaces')) as fh:
            contents = fh.read()
        print(contents)
        expected = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
"""
        self.assertEqual(expected.lstrip(), contents.lstrip())

        self.assertTrue(os.path.exists(os.path.join(render_dir, 'netrules')))
        with open(os.path.join(render_dir, 'netrules')) as fh:
            contents = fh.read()
        print(contents)
        expected_rule = [
            'SUBSYSTEM=="net"',
            'ACTION=="add"',
            'DRIVERS=="hv_netsvc"',
            'ATTR{address}=="00:11:22:33:44:55"',
            'NAME="eth0"',
        ]
        self.assertEqual(", ".join(expected_rule) + '\n', contents.lstrip())

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_device_driver_blacklist(self, mock_get_devicelist,
                                     mock_read_sys_net, mock_sys_dev_path):
        devices = {
            'eth1': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'hv_netsvc', 'device/device': '0x3',
                'name_assign_type': '4'},
            'eth0': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'mlx4_core', 'device/device': '0x7',
                'name_assign_type': '4'},
        }

        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path,
                    dev_attrs=devices)

        blacklist = ['mlx4_core']
        network_cfg = net.generate_fallback_config(blacklist_drivers=blacklist,
                                                   config_driver=True)
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        # don't set rulepath so eni writes them
        renderer = eni.Renderer(
            {'eni_path': 'interfaces', 'netrules_path': 'netrules'})
        renderer.render_network_state(ns, target=render_dir)

        self.assertTrue(os.path.exists(os.path.join(render_dir,
                                                    'interfaces')))
        with open(os.path.join(render_dir, 'interfaces')) as fh:
            contents = fh.read()
        print(contents)
        expected = """
auto lo
iface lo inet loopback

auto eth1
iface eth1 inet dhcp
"""
        self.assertEqual(expected.lstrip(), contents.lstrip())

        self.assertTrue(os.path.exists(os.path.join(render_dir, 'netrules')))
        with open(os.path.join(render_dir, 'netrules')) as fh:
            contents = fh.read()
        print(contents)
        expected_rule = [
            'SUBSYSTEM=="net"',
            'ACTION=="add"',
            'DRIVERS=="hv_netsvc"',
            'ATTR{address}=="00:11:22:33:44:55"',
            'NAME="eth1"',
        ]
        self.assertEqual(", ".join(expected_rule) + '\n', contents.lstrip())

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("cloudinit.util.udevadm_settle")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_unstable_names(self, mock_get_devicelist, mock_read_sys_net,
                            mock_sys_dev_path, mock_settle, m_get_cmdline):
        """verify that udevadm settle is called when we find unstable names"""
        devices = {
            'eth0': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'hv_netsvc', 'device/device': '0x3',
                'name_assign_type': False},
            'ens4': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'mlx4_core', 'device/device': '0x7',
                'name_assign_type': '4'},

        }

        m_get_cmdline.return_value = ''
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path,
                    dev_attrs=devices)
        net.generate_fallback_config(config_driver=True)
        self.assertEqual(1, mock_settle.call_count)

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("cloudinit.util.udevadm_settle")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_unstable_names_disabled(self, mock_get_devicelist,
                                     mock_read_sys_net, mock_sys_dev_path,
                                     mock_settle, m_get_cmdline):
        """verify udevadm settle not called when cmdline has net.ifnames=0"""
        devices = {
            'eth0': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'hv_netsvc', 'device/device': '0x3',
                'name_assign_type': False},
            'ens4': {
                'bridge': False, 'carrier': False, 'dormant': False,
                'operstate': 'down', 'address': '00:11:22:33:44:55',
                'device/driver': 'mlx4_core', 'device/device': '0x7',
                'name_assign_type': '4'},

        }

        m_get_cmdline.return_value = 'net.ifnames=0'
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path,
                    dev_attrs=devices)
        net.generate_fallback_config(config_driver=True)
        self.assertEqual(0, mock_settle.call_count)


class TestRhelSysConfigRendering(CiTestCase):

    with_logs = True

    nm_cfg_file = "/etc/NetworkManager/NetworkManager.conf"
    scripts_dir = '/etc/sysconfig/network-scripts'
    header = ('# Created by cloud-init on instance boot automatically, '
              'do not edit.\n#\n')

    expected_name = 'expected_sysconfig_rhel'

    def _get_renderer(self):
        distro_cls = distros.fetch('rhel')
        return sysconfig.Renderer(
            config=distro_cls.renderer_configs.get('sysconfig'))

    def _render_and_read(self, network_config=None, state=None, dir=None):
        if dir is None:
            dir = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=dir)
        return dir2dict(dir)

    def _compare_files_to_expected(self, expected, found):

        def _try_load(f):
            ''' Attempt to load shell content, otherwise return as-is '''
            try:
                return util.load_shell_content(f)
            except ValueError:
                pass
            # route6- * files aren't shell content, but iproute2 params
            return f

        orig_maxdiff = self.maxDiff
        expected_d = dict(
            (os.path.join(self.scripts_dir, k), _try_load(v))
            for k, v in expected.items())

        # only compare the files in scripts_dir
        scripts_found = dict(
            (k, _try_load(v)) for k, v in found.items()
            if k.startswith(self.scripts_dir))
        try:
            self.maxDiff = None
            self.assertEqual(expected_d, scripts_found)
        finally:
            self.maxDiff = orig_maxdiff

    def _assert_headers(self, found):
        missing = [f for f in found
                   if (f.startswith(self.scripts_dir) and
                       not found[f].startswith(self.header))]
        if missing:
            raise AssertionError("Missing headers in: %s" % missing)

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path, m_get_cmdline):
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)

        render_file = 'etc/sysconfig/network-scripts/ifcfg-eth1000'
        with open(os.path.join(render_dir, render_file)) as fh:
            content = fh.read()
            expected_content = """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1000
HWADDR=07-1c-c6-75-a4-be
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()
            self.assertEqual(expected_content, content)

    def test_multiple_ipv4_default_gateways(self):
        """ValueError is raised when duplicate ipv4 gateways exist."""
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [{
                "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                "type": "ipv4", "netmask": "255.255.252.0",
                "link": "tap1a81968a-79",
                "routes": [{
                    "netmask": "0.0.0.0",
                    "network": "0.0.0.0",
                    "gateway": "172.19.3.254",
                }, {
                    "netmask": "0.0.0.0",  # A second default gateway
                    "network": "0.0.0.0",
                    "gateway": "172.20.3.254",
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
        }
        macs = {'fa:16:3e:ed:9a:59': 'eth0'}
        render_dir = self.tmp_dir()
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)
        renderer = self._get_renderer()
        with self.assertRaises(ValueError):
            renderer.render_network_state(ns, target=render_dir)
        self.assertEqual([], os.listdir(render_dir))

    def test_multiple_ipv6_default_gateways(self):
        """ValueError is raised when duplicate ipv6 gateways exist."""
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [{
                "network_id": "public-ipv6",
                "type": "ipv6", "netmask": "",
                "link": "tap1a81968a-79",
                "routes": [{
                    "gateway": "2001:DB8::1",
                    "netmask": "::",
                    "network": "::"
                }, {
                    "gateway": "2001:DB9::1",
                    "netmask": "::",
                    "network": "::"
                }],
                "ip_address": "2001:DB8::10", "id": "network1"
            }],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None, "type": "bridge", "id":
                    "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f"
                },
            ],
        }
        macs = {'fa:16:3e:ed:9a:59': 'eth0'}
        render_dir = self.tmp_dir()
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)
        renderer = self._get_renderer()
        with self.assertRaises(ValueError):
            renderer.render_network_state(ns, target=render_dir)
        self.assertEqual([], os.listdir(render_dir))

    def test_openstack_rendering_samples(self):
        for os_sample in OS_SAMPLES:
            render_dir = self.tmp_dir()
            ex_input = os_sample['in_data']
            ex_mac_addrs = os_sample['in_macs']
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs)
            ns = network_state.parse_net_config_data(network_cfg,
                                                     skip_broken=False)
            renderer = self._get_renderer()
            # render a multiple times to simulate reboots
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            for fn, expected_content in os_sample.get('out_sysconfig_rhel',
                                                      []):
                with open(os.path.join(render_dir, fn)) as fh:
                    self.assertEqual(expected_content, fh.read())

    def test_network_config_v1_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_SIMPLE_SUBNET)
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = '/etc/sysconfig/network-scripts/'
        self.assertNotIn(nspath + 'ifcfg-lo', found.keys())
        expected = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=interface0
GATEWAY=10.0.2.2
HWADDR=52:54:00:12:34:00
IPADDR=10.0.2.15
NETMASK=255.255.255.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        self.assertEqual(expected, found[nspath + 'ifcfg-interface0'])
        # The configuration has no nameserver information make sure we
        # do not write the resolv.conf file
        respath = '/etc/resolv.conf'
        self.assertNotIn(respath, found.keys())

    def test_network_config_v1_multi_iface_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_MULTI_IFACE)
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = '/etc/sysconfig/network-scripts/'
        self.assertNotIn(nspath + 'ifcfg-lo', found.keys())
        expected_i1 = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
GATEWAY=51.68.80.1
HWADDR=fa:16:3e:25:b4:59
IPADDR=51.68.89.122
MTU=1500
NETMASK=255.255.240.0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        self.assertEqual(expected_i1, found[nspath + 'ifcfg-eth0'])
        expected_i2 = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1
DHCLIENT_SET_DEFAULT_ROUTE=no
HWADDR=fa:16:3e:b1:ca:29
MTU=9000
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        self.assertEqual(expected_i2, found[nspath + 'ifcfg-eth1'])

    def test_config_with_explicit_loopback(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        # write an etc/resolv.conf and expect it to not be modified
        resolvconf = os.path.join(render_dir, 'etc/resolv.conf')
        resolvconf_content = "# Original Content"
        util.write_file(resolvconf, resolvconf_content)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = '/etc/sysconfig/network-scripts/'
        self.assertNotIn(nspath + 'ifcfg-lo', found.keys())
        expected = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth0
NM_CONTROLLED=no
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        self.assertEqual(expected, found[nspath + 'ifcfg-eth0'])
        # a dhcp only config should not modify resolv.conf
        self.assertEqual(resolvconf_content, found['/etc/resolv.conf'])

    def test_bond_config(self):
        entry = NETWORK_CONFIGS['bond']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_vlan_config(self):
        entry = NETWORK_CONFIGS['vlan']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_bridge_config(self):
        entry = NETWORK_CONFIGS['bridge']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_manual_config(self):
        entry = NETWORK_CONFIGS['manual']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_all_config(self):
        entry = NETWORK_CONFIGS['all']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        self.assertNotIn(
            'WARNING: Network config: ignoring eth0.101 device-level mtu',
            self.logs.getvalue())

    def test_small_config(self):
        entry = NETWORK_CONFIGS['small']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_v4_and_v6_static_config(self):
        entry = NETWORK_CONFIGS['v4_and_v6_static']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        expected_msg = (
            'WARNING: Network config: ignoring iface0 device-level mtu:8999'
            ' because ipv4 subnet-level mtu:9000 provided.')
        self.assertIn(expected_msg, self.logs.getvalue())

    def test_dhcpv6_only_config(self):
        entry = NETWORK_CONFIGS['dhcpv6_only']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_accept_ra_config_v1(self):
        entry = NETWORK_CONFIGS['dhcpv6_accept_ra']
        found = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_accept_ra_config_v2(self):
        entry = NETWORK_CONFIGS['dhcpv6_accept_ra']
        found = self._render_and_read(network_config=yaml.load(
            entry['yaml_v2']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_reject_ra_config_v1(self):
        entry = NETWORK_CONFIGS['dhcpv6_reject_ra']
        found = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_reject_ra_config_v2(self):
        entry = NETWORK_CONFIGS['dhcpv6_reject_ra']
        found = self._render_and_read(network_config=yaml.load(
            entry['yaml_v2']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_stateless_config(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateless']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_stateful_config(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateful']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_check_ifcfg_rh(self):
        """ifcfg-rh plugin is added NetworkManager.conf if conf present."""
        render_dir = self.tmp_dir()
        nm_cfg = util.target_path(render_dir, path=self.nm_cfg_file)
        util.ensure_dir(os.path.dirname(nm_cfg))

        # write a template nm.conf, note plugins is a list here
        with open(nm_cfg, 'w') as fh:
            fh.write('# test_check_ifcfg_rh\n[main]\nplugins=foo,bar\n')
        self.assertTrue(os.path.exists(nm_cfg))

        # render and read
        entry = NETWORK_CONFIGS['small']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']),
                                      dir=render_dir)
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

        # check ifcfg-rh is in the 'plugins' list
        config = sysconfig.ConfigObj(nm_cfg)
        self.assertIn('ifcfg-rh', config['main']['plugins'])

    def test_check_ifcfg_rh_plugins_string(self):
        """ifcfg-rh plugin is append when plugins is a string."""
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        nm_cfg = util.target_path(render_dir, path=self.nm_cfg_file)
        util.ensure_dir(os.path.dirname(nm_cfg))

        # write a template nm.conf, note plugins is a value here
        util.write_file(nm_cfg, '# test_check_ifcfg_rh\n[main]\nplugins=foo\n')

        # render and read
        entry = NETWORK_CONFIGS['small']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']),
                                      dir=render_dir)
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

        # check raw content has plugin
        nm_file_content = util.load_file(nm_cfg)
        self.assertIn('ifcfg-rh', nm_file_content)

        # check ifcfg-rh is in the 'plugins' list
        config = sysconfig.ConfigObj(nm_cfg)
        self.assertIn('ifcfg-rh', config['main']['plugins'])

    def test_check_ifcfg_rh_plugins_no_plugins(self):
        """enable_ifcfg_plugin creates plugins value if missing."""
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        nm_cfg = util.target_path(render_dir, path=self.nm_cfg_file)
        util.ensure_dir(os.path.dirname(nm_cfg))

        # write a template nm.conf, note plugins is missing
        util.write_file(nm_cfg, '# test_check_ifcfg_rh\n[main]\n')
        self.assertTrue(os.path.exists(nm_cfg))

        # render and read
        entry = NETWORK_CONFIGS['small']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']),
                                      dir=render_dir)
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

        # check ifcfg-rh is in the 'plugins' list
        config = sysconfig.ConfigObj(nm_cfg)
        self.assertIn('ifcfg-rh', config['main']['plugins'])

    def test_netplan_dhcp_false_disable_dhcp_in_state(self):
        """netplan config with dhcp[46]: False should not add dhcp in state"""
        net_config = yaml.load(NETPLAN_DHCP_FALSE)
        ns = network_state.parse_net_config_data(net_config,
                                                 skip_broken=False)

        dhcp_found = [snet for iface in ns.iter_interfaces()
                      for snet in iface['subnets'] if 'dhcp' in snet['type']]

        self.assertEqual([], dhcp_found)

    def test_netplan_dhcp_false_no_dhcp_in_sysconfig(self):
        """netplan cfg with dhcp[46]: False should not have bootproto=dhcp"""

        entry = {
            'yaml': NETPLAN_DHCP_FALSE,
            'expected_sysconfig': {
                'ifcfg-ens3': textwrap.dedent("""\
                   BOOTPROTO=none
                   DEFROUTE=yes
                   DEVICE=ens3
                   DNS1=192.168.42.53
                   DNS2=1.1.1.1
                   DOMAIN=example.com
                   GATEWAY=192.168.42.1
                   HWADDR=52:54:00:ab:cd:ef
                   IPADDR=192.168.42.100
                   IPV6ADDR=2001:db8::100/32
                   IPV6INIT=yes
                   IPV6_DEFAULTGW=2001:db8::1
                   NETMASK=255.255.255.0
                   NM_CONTROLLED=no
                   ONBOOT=yes
                   TYPE=Ethernet
                   USERCTL=no
                   """),
            }
        }

        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry['expected_sysconfig'], found)
        self._assert_headers(found)

    def test_from_v2_vlan_mtu(self):
        """verify mtu gets rendered on bond when source is netplan."""
        v2data = {
            'version': 2,
            'ethernets': {'eno1': {}},
            'vlans': {
                'eno1.1000': {
                    'addresses': ["192.6.1.9/24"],
                    'id': 1000, 'link': 'eno1', 'mtu': 1495}}}
        expected = {
            'ifcfg-eno1': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eno1
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            'ifcfg-eno1.1000': textwrap.dedent("""\
                BOOTPROTO=none
                DEVICE=eno1.1000
                IPADDR=192.6.1.9
                MTU=1495
                NETMASK=255.255.255.0
                NM_CONTROLLED=no
                ONBOOT=yes
                PHYSDEV=eno1
                TYPE=Ethernet
                USERCTL=no
                VLAN=yes
                """)
            }
        self._compare_files_to_expected(
            expected, self._render_and_read(network_config=v2data))

    def test_from_v2_bond_mtu(self):
        """verify mtu gets rendered on bond when source is netplan."""
        v2data = {
            'version': 2,
            'bonds': {
                'bond0': {'addresses': ['10.101.8.65/26'],
                          'interfaces': ['enp0s0', 'enp0s1'],
                          'mtu': 1334,
                          'parameters': {}}}
        }
        expected = {
            'ifcfg-bond0': textwrap.dedent("""\
                BONDING_MASTER=yes
                BONDING_SLAVE0=enp0s0
                BONDING_SLAVE1=enp0s1
                BOOTPROTO=none
                DEVICE=bond0
                IPADDR=10.101.8.65
                MTU=1334
                NETMASK=255.255.255.192
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Bond
                USERCTL=no
                """),
            'ifcfg-enp0s0': textwrap.dedent("""\
                BONDING_MASTER=yes
                BOOTPROTO=none
                DEVICE=enp0s0
                MASTER=bond0
                NM_CONTROLLED=no
                ONBOOT=yes
                SLAVE=yes
                TYPE=Bond
                USERCTL=no
                """),
            'ifcfg-enp0s1': textwrap.dedent("""\
                BONDING_MASTER=yes
                BOOTPROTO=none
                DEVICE=enp0s1
                MASTER=bond0
                NM_CONTROLLED=no
                ONBOOT=yes
                SLAVE=yes
                TYPE=Bond
                USERCTL=no
                """)
        }
        self._compare_files_to_expected(
            expected, self._render_and_read(network_config=v2data))

    def test_from_v2_route_metric(self):
        """verify route-metric gets rendered on nic when source is netplan."""
        overrides = {'route-metric': 100}
        v2base = {
            'version': 2,
            'ethernets': {
                'eno1': {'dhcp4': True,
                         'match': {'macaddress': '07-1c-c6-75-a4-be'}}}}
        expected = {
            'ifcfg-eno1': textwrap.dedent("""\
                BOOTPROTO=dhcp
                DEVICE=eno1
                HWADDR=07-1c-c6-75-a4-be
                METRIC=100
                NM_CONTROLLED=no
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """),
            }
        for dhcp_ver in ('dhcp4', 'dhcp6'):
            v2data = copy.deepcopy(v2base)
            if dhcp_ver == 'dhcp6':
                expected['ifcfg-eno1'] += "IPV6INIT=yes\nDHCPV6C=yes\n"
            v2data['ethernets']['eno1'].update(
                {dhcp_ver: True, '{0}-overrides'.format(dhcp_ver): overrides})
            self._compare_files_to_expected(
                expected, self._render_and_read(network_config=v2data))


class TestOpenSuseSysConfigRendering(CiTestCase):

    with_logs = True

    scripts_dir = '/etc/sysconfig/network'
    header = ('# Created by cloud-init on instance boot automatically, '
              'do not edit.\n#\n')

    expected_name = 'expected_sysconfig_opensuse'

    def _get_renderer(self):
        distro_cls = distros.fetch('opensuse')
        return sysconfig.Renderer(
            config=distro_cls.renderer_configs.get('sysconfig'))

    def _render_and_read(self, network_config=None, state=None, dir=None):
        if dir is None:
            dir = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=dir)
        return dir2dict(dir)

    def _compare_files_to_expected(self, expected, found):
        orig_maxdiff = self.maxDiff
        expected_d = dict(
            (os.path.join(self.scripts_dir, k), util.load_shell_content(v))
            for k, v in expected.items())

        # only compare the files in scripts_dir
        scripts_found = dict(
            (k, util.load_shell_content(v)) for k, v in found.items()
            if k.startswith(self.scripts_dir))
        try:
            self.maxDiff = None
            self.assertEqual(expected_d, scripts_found)
        finally:
            self.maxDiff = orig_maxdiff

    def _assert_headers(self, found):
        missing = [f for f in found
                   if (f.startswith(self.scripts_dir) and
                       not found[f].startswith(self.header))]
        if missing:
            raise AssertionError("Missing headers in: %s" % missing)

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path, m_get_cmdline):
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)

        render_file = 'etc/sysconfig/network/ifcfg-eth1000'
        with open(os.path.join(render_dir, render_file)) as fh:
            content = fh.read()
            expected_content = """
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp4
LLADDR=07-1c-c6-75-a4-be
STARTMODE=auto
""".lstrip()
            self.assertEqual(expected_content, content)

    # TODO(rjschwei): re-enable test once route writing is implemented
    # for SUSE distros
#    def test_multiple_ipv4_default_gateways(self):
#        """ValueError is raised when duplicate ipv4 gateways exist."""
#        net_json = {
#            "services": [{"type": "dns", "address": "172.19.0.12"}],
#            "networks": [{
#                "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
#                "type": "ipv4", "netmask": "255.255.252.0",
#                "link": "tap1a81968a-79",
#                "routes": [{
#                    "netmask": "0.0.0.0",
#                    "network": "0.0.0.0",
#                    "gateway": "172.19.3.254",
#                }, {
#                    "netmask": "0.0.0.0",  # A second default gateway
#                    "network": "0.0.0.0",
#                    "gateway": "172.20.3.254",
#                }],
#                "ip_address": "172.19.1.34", "id": "network0"
#            }],
#            "links": [
#                {
#                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
#                    "mtu": None, "type": "bridge", "id":
#                    "tap1a81968a-79",
#                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f"
#                },
#            ],
#        }
#        macs = {'fa:16:3e:ed:9a:59': 'eth0'}
#        render_dir = self.tmp_dir()
#        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
#        ns = network_state.parse_net_config_data(network_cfg,
#                                                 skip_broken=False)
#        renderer = self._get_renderer()
#        with self.assertRaises(ValueError):
#            renderer.render_network_state(ns, target=render_dir)
#        self.assertEqual([], os.listdir(render_dir))
#
#    def test_multiple_ipv6_default_gateways(self):
#        """ValueError is raised when duplicate ipv6 gateways exist."""
#        net_json = {
#            "services": [{"type": "dns", "address": "172.19.0.12"}],
#            "networks": [{
#                "network_id": "public-ipv6",
#                "type": "ipv6", "netmask": "",
#                "link": "tap1a81968a-79",
#                "routes": [{
#                    "gateway": "2001:DB8::1",
#                    "netmask": "::",
#                    "network": "::"
#                }, {
#                    "gateway": "2001:DB9::1",
#                    "netmask": "::",
#                    "network": "::"
#                }],
#                "ip_address": "2001:DB8::10", "id": "network1"
#            }],
#            "links": [
#                {
#                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
#                    "mtu": None, "type": "bridge", "id":
#                    "tap1a81968a-79",
#                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f"
#                },
#            ],
#        }
#        macs = {'fa:16:3e:ed:9a:59': 'eth0'}
#        render_dir = self.tmp_dir()
#        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
#        ns = network_state.parse_net_config_data(network_cfg,
#                                                 skip_broken=False)
#        renderer = self._get_renderer()
#        with self.assertRaises(ValueError):
#            renderer.render_network_state(ns, target=render_dir)
#        self.assertEqual([], os.listdir(render_dir))

    def test_openstack_rendering_samples(self):
        for os_sample in OS_SAMPLES:
            render_dir = self.tmp_dir()
            ex_input = os_sample['in_data']
            ex_mac_addrs = os_sample['in_macs']
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs)
            ns = network_state.parse_net_config_data(network_cfg,
                                                     skip_broken=False)
            renderer = self._get_renderer()
            # render a multiple times to simulate reboots
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            for fn, expected_content in os_sample.get('out_sysconfig_opensuse',
                                                      []):
                with open(os.path.join(render_dir, fn)) as fh:
                    self.assertEqual(expected_content, fh.read())

    def test_network_config_v1_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_SIMPLE_SUBNET)
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = '/etc/sysconfig/network/'
        self.assertNotIn(nspath + 'ifcfg-lo', found.keys())
        expected = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=static
IPADDR=10.0.2.15
LLADDR=52:54:00:12:34:00
NETMASK=255.255.255.0
STARTMODE=auto
"""
        self.assertEqual(expected, found[nspath + 'ifcfg-interface0'])
        # The configuration has no nameserver information make sure we
        # do not write the resolv.conf file
        respath = '/etc/resolv.conf'
        self.assertNotIn(respath, found.keys())

    def test_config_with_explicit_loopback(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        render_dir = self.tmp_path("render")
        os.makedirs(render_dir)
        # write an etc/resolv.conf and expect it to not be modified
        resolvconf = os.path.join(render_dir, 'etc/resolv.conf')
        resolvconf_content = "# Original Content"
        util.write_file(resolvconf, resolvconf_content)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = '/etc/sysconfig/network/'
        self.assertNotIn(nspath + 'ifcfg-lo', found.keys())
        expected = """\
# Created by cloud-init on instance boot automatically, do not edit.
#
BOOTPROTO=dhcp
STARTMODE=auto
"""
        self.assertEqual(expected, found[nspath + 'ifcfg-eth0'])
        # a dhcp only config should not modify resolv.conf
        self.assertEqual(resolvconf_content, found['/etc/resolv.conf'])

    def test_bond_config(self):
        expected_name = 'expected_sysconfig_opensuse'
        entry = NETWORK_CONFIGS['bond']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        for fname, contents in entry[expected_name].items():
            print(fname)
            print(contents)
            print()
        print('-- expected ^ | v rendered --')
        for fname, contents in found.items():
            print(fname)
            print(contents)
            print()
        self._compare_files_to_expected(entry[expected_name], found)
        self._assert_headers(found)

    def test_vlan_config(self):
        entry = NETWORK_CONFIGS['vlan']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_bridge_config(self):
        entry = NETWORK_CONFIGS['bridge']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_manual_config(self):
        entry = NETWORK_CONFIGS['manual']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_all_config(self):
        entry = NETWORK_CONFIGS['all']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        self.assertNotIn(
            'WARNING: Network config: ignoring eth0.101 device-level mtu',
            self.logs.getvalue())

    def test_small_config(self):
        entry = NETWORK_CONFIGS['small']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_v4_and_v6_static_config(self):
        entry = NETWORK_CONFIGS['v4_and_v6_static']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        expected_msg = (
            'WARNING: Network config: ignoring iface0 device-level mtu:8999'
            ' because ipv4 subnet-level mtu:9000 provided.')
        self.assertIn(expected_msg, self.logs.getvalue())

    def test_dhcpv6_only_config(self):
        entry = NETWORK_CONFIGS['dhcpv6_only']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_simple_render_ipv6_slaac(self):
        entry = NETWORK_CONFIGS['ipv6_slaac']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_dhcpv6_stateless_config(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateless']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_render_v4_and_v6(self):
        entry = NETWORK_CONFIGS['v4_and_v6']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_render_v6_and_v4(self):
        entry = NETWORK_CONFIGS['v6_and_v4']
        found = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)


class TestEniNetRendering(CiTestCase):

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path, m_get_cmdline):
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = eni.Renderer(
            {'eni_path': 'interfaces', 'netrules_path': None})
        renderer.render_network_state(ns, target=render_dir)

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

    def test_config_with_explicit_loopback(self):
        tmp_dir = self.tmp_dir()
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        renderer = eni.Renderer()
        renderer.render_network_state(ns, target=tmp_dir)
        expected = """\
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
"""
        self.assertEqual(
            expected, dir2dict(tmp_dir)['/etc/network/interfaces'])

    def test_v2_route_metric_to_eni(self):
        """Network v2 route-metric overrides are preserved in eni output"""
        tmp_dir = self.tmp_dir()
        renderer = eni.Renderer()
        expected_tmpl = textwrap.dedent("""\
            auto lo
            iface lo inet loopback

            auto eth0
            iface eth0 inet{suffix} dhcp
                metric 100
            """)
        for dhcp_ver in ('dhcp4', 'dhcp6'):
            suffix = '6' if dhcp_ver == 'dhcp6' else ''
            dhcp_cfg = {
                dhcp_ver: True,
                '{ver}-overrides'.format(ver=dhcp_ver): {'route-metric': 100}}
            v2_input = {'version': 2, 'ethernets': {'eth0': dhcp_cfg}}
            ns = network_state.parse_net_config_data(v2_input)
            renderer.render_network_state(ns, target=tmp_dir)
            self.assertEqual(
                expected_tmpl.format(suffix=suffix),
                dir2dict(tmp_dir)['/etc/network/interfaces'])


class TestNetplanNetRendering(CiTestCase):

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.netplan._clean_default")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(self, mock_get_devicelist,
                                mock_read_sys_net,
                                mock_sys_dev_path,
                                mock_clean_default, m_get_cmdline):
        tmp_dir = self.tmp_dir()
        _setup_test(tmp_dir, mock_get_devicelist,
                    mock_read_sys_net, mock_sys_dev_path)

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(network_cfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = 'netplan.yaml'
        renderer = netplan.Renderer(
            {'netplan_path': render_target, 'postcmds': False})
        renderer.render_network_state(ns, target=render_dir)

        self.assertTrue(os.path.exists(os.path.join(render_dir,
                                                    render_target)))
        with open(os.path.join(render_dir, render_target)) as fh:
            contents = fh.read()
            print(contents)

        expected = """
network:
    ethernets:
        eth1000:
            dhcp4: true
            match:
                macaddress: 07-1c-c6-75-a4-be
            set-name: eth1000
    version: 2
"""
        self.assertEqual(expected.lstrip(), contents.lstrip())
        self.assertEqual(1, mock_clean_default.call_count)


class TestNetplanCleanDefault(CiTestCase):
    snapd_known_path = 'etc/netplan/00-snapd-config.yaml'
    snapd_known_content = textwrap.dedent("""\
        # This is the initial network config.
        # It can be overwritten by cloud-init or console-conf.
        network:
            version: 2
            ethernets:
                all-en:
                    match:
                        name: "en*"
                    dhcp4: true
                all-eth:
                    match:
                        name: "eth*"
                    dhcp4: true
        """)
    stub_known = {
        'run/systemd/network/10-netplan-all-en.network': 'foo-en',
        'run/systemd/network/10-netplan-all-eth.network': 'foo-eth',
        'run/systemd/generator/netplan.stamp': 'stamp',
    }

    def test_clean_known_config_cleaned(self):
        content = {self.snapd_known_path: self.snapd_known_content, }
        content.update(self.stub_known)
        tmpd = self.tmp_dir()
        files = sorted(populate_dir(tmpd, content))
        netplan._clean_default(target=tmpd)
        found = [t for t in files if os.path.exists(t)]
        self.assertEqual([], found)

    def test_clean_unknown_config_not_cleaned(self):
        content = {self.snapd_known_path: self.snapd_known_content, }
        content.update(self.stub_known)
        content[self.snapd_known_path] += "# user put a comment\n"
        tmpd = self.tmp_dir()
        files = sorted(populate_dir(tmpd, content))
        netplan._clean_default(target=tmpd)
        found = [t for t in files if os.path.exists(t)]
        self.assertEqual(files, found)

    def test_clean_known_config_cleans_only_expected(self):
        astamp = "run/systemd/generator/another.stamp"
        anet = "run/systemd/network/10-netplan-all-lo.network"
        ayaml = "etc/netplan/01-foo-config.yaml"
        content = {
            self.snapd_known_path: self.snapd_known_content,
            astamp: "stamp",
            anet: "network",
            ayaml: "yaml",
        }
        content.update(self.stub_known)

        tmpd = self.tmp_dir()
        files = sorted(populate_dir(tmpd, content))
        netplan._clean_default(target=tmpd)
        found = [t for t in files if os.path.exists(t)]
        expected = [util.target_path(tmpd, f) for f in (astamp, anet, ayaml)]
        self.assertEqual(sorted(expected), found)


class TestNetplanPostcommands(CiTestCase):
    mycfg = {
        'config': [{"type": "physical", "name": "eth0",
                    "mac_address": "c0:d6:9f:2c:e8:80",
                    "subnets": [{"type": "dhcp"}]}],
        'version': 1}

    @mock.patch.object(netplan.Renderer, '_netplan_generate')
    @mock.patch.object(netplan.Renderer, '_net_setup_link')
    @mock.patch('cloudinit.util.subp')
    def test_netplan_render_calls_postcmds(self, mock_subp,
                                           mock_netplan_generate,
                                           mock_net_setup_link):
        tmp_dir = self.tmp_dir()
        ns = network_state.parse_net_config_data(self.mycfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = 'netplan.yaml'
        renderer = netplan.Renderer(
            {'netplan_path': render_target, 'postcmds': True})
        mock_subp.side_effect = iter([util.ProcessExecutionError])
        renderer.render_network_state(ns, target=render_dir)

        mock_netplan_generate.assert_called_with(run=True)
        mock_net_setup_link.assert_called_with(run=True)

    @mock.patch('cloudinit.util.SeLinuxGuard')
    @mock.patch.object(netplan, "get_devicelist")
    @mock.patch('cloudinit.util.subp')
    def test_netplan_postcmds(self, mock_subp, mock_devlist, mock_sel):
        mock_sel.__enter__ = mock.Mock(return_value=False)
        mock_sel.__exit__ = mock.Mock()
        mock_devlist.side_effect = [['lo']]
        tmp_dir = self.tmp_dir()
        ns = network_state.parse_net_config_data(self.mycfg,
                                                 skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = 'netplan.yaml'
        renderer = netplan.Renderer(
            {'netplan_path': render_target, 'postcmds': True})
        mock_subp.side_effect = iter([
            util.ProcessExecutionError,
            ('', ''),
            ('', ''),
        ])
        expected = [
            mock.call(['netplan', 'info'], capture=True),
            mock.call(['netplan', 'generate'], capture=True),
            mock.call(['udevadm', 'test-builtin', 'net_setup_link',
                       '/sys/class/net/lo'], capture=True),
        ]
        with mock.patch.object(os.path, 'islink', return_value=True):
            renderer.render_network_state(ns, target=render_dir)
            mock_subp.assert_has_calls(expected)


class TestEniNetworkStateToEni(CiTestCase):
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


class TestCmdlineConfigParsing(CiTestCase):
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


class TestNetplanRoundTrip(CiTestCase):

    NETPLAN_INFO_OUT = textwrap.dedent("""
    netplan.io:
      features:
        - dhcp-use-domains
        - ipv6-mtu
      website: https://netplan.io/
    """)

    def setUp(self):
        super(TestNetplanRoundTrip, self).setUp()
        self.add_patch('cloudinit.net.netplan.util.subp', 'm_subp')
        self.m_subp.return_value = (self.NETPLAN_INFO_OUT, '')

    def _render_and_read(self, network_config=None, state=None,
                         netplan_path=None, target=None):
        if target is None:
            target = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if netplan_path is None:
            netplan_path = 'etc/netplan/50-cloud-init.yaml'

        renderer = netplan.Renderer(
            config={'netplan_path': netplan_path})

        renderer.render_network_state(ns, target=target)
        return dir2dict(target)

    def testsimple_render_bond_netplan(self):
        entry = NETWORK_CONFIGS['bond']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        print(entry['expected_netplan'])
        print('-- expected ^ | v rendered --')
        print(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_bond_v2_input_netplan(self):
        entry = NETWORK_CONFIGS['bond']
        files = self._render_and_read(
            network_config=yaml.load(entry['yaml-v2']))
        print(entry['expected_netplan-v2'])
        print('-- expected ^ | v rendered --')
        print(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertEqual(
            entry['expected_netplan-v2'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_small_netplan(self):
        entry = NETWORK_CONFIGS['small']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_v4_and_v6(self):
        entry = NETWORK_CONFIGS['v4_and_v6']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_v4_and_v6_static(self):
        entry = NETWORK_CONFIGS['v4_and_v6_static']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_dhcpv6_only(self):
        entry = NETWORK_CONFIGS['dhcpv6_only']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_dhcpv6_accept_ra(self):
        entry = NETWORK_CONFIGS['dhcpv6_accept_ra']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_dhcpv6_reject_ra(self):
        entry = NETWORK_CONFIGS['dhcpv6_reject_ra']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_ipv6_slaac(self):
        entry = NETWORK_CONFIGS['ipv6_slaac']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_dhcpv6_stateless(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateless']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_dhcpv6_stateful(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateful']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_all(self):
        entry = NETWORK_CONFIGS['all']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        print(entry['expected_netplan'])
        print('-- expected ^ | v rendered --')
        print(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def testsimple_render_manual(self):
        entry = NETWORK_CONFIGS['manual']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def test_render_output_has_yaml_no_aliases(self):
        entry = {
            'yaml': V1_NAMESERVER_ALIAS,
            'expected_netplan': NETPLAN_NO_ALIAS,
        }
        network_config = yaml.load(entry['yaml'])
        ns = network_state.parse_net_config_data(network_config)
        files = self._render_and_read(state=ns)
        # check for alias
        content = files['/etc/netplan/50-cloud-init.yaml']

        # test load the yaml to ensure we don't render something not loadable
        # this allows single aliases, but not duplicate ones
        parsed = yaml.load(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertNotEqual(None, parsed)

        # now look for any alias, avoid rendering them entirely
        # generate the first anchor string using the template
        # as of this writing, looks like "&id001"
        anchor = r'&' + Serializer.ANCHOR_TEMPLATE % 1
        found_alias = re.search(anchor, content, re.MULTILINE)
        if found_alias:
            msg = "Error at: %s\nContent:\n%s" % (found_alias, content)
            raise ValueError('Found yaml alias in rendered netplan: ' + msg)

        print(entry['expected_netplan'])
        print('-- expected ^ | v rendered --')
        print(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())

    def test_render_output_supports_both_grat_arp_spelling(self):
        entry = {
            'yaml': NETPLAN_BOND_GRAT_ARP,
            'expected_netplan': NETPLAN_BOND_GRAT_ARP.replace('gratuitous',
                                                              'gratuitious'),
        }
        network_config = yaml.load(entry['yaml']).get('network')
        files = self._render_and_read(network_config=network_config)
        print(entry['expected_netplan'])
        print('-- expected ^ | v rendered --')
        print(files['/etc/netplan/50-cloud-init.yaml'])
        self.assertEqual(
            entry['expected_netplan'].splitlines(),
            files['/etc/netplan/50-cloud-init.yaml'].splitlines())


class TestEniRoundTrip(CiTestCase):

    def _render_and_read(self, network_config=None, state=None, eni_path=None,
                         netrules_path=None, dir=None):
        if dir is None:
            dir = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if eni_path is None:
            eni_path = 'etc/network/interfaces'

        renderer = eni.Renderer(
            config={'eni_path': eni_path, 'netrules_path': netrules_path})

        renderer.render_network_state(ns, target=dir)
        return dir2dict(dir)

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

    def testsimple_render_v4_and_v6(self):
        entry = NETWORK_CONFIGS['v4_and_v6']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_dhcpv6_only(self):
        entry = NETWORK_CONFIGS['dhcpv6_only']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_v4_and_v6_static(self):
        entry = NETWORK_CONFIGS['v4_and_v6_static']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_dhcpv6_stateless(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateless']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_ipv6_slaac(self):
        entry = NETWORK_CONFIGS['ipv6_slaac']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_dhcpv6_stateful(self):
        entry = NETWORK_CONFIGS['dhcpv6_stateless']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_dhcpv6_accept_ra(self):
        entry = NETWORK_CONFIGS['dhcpv6_accept_ra']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_dhcpv6_reject_ra(self):
        entry = NETWORK_CONFIGS['dhcpv6_reject_ra']
        files = self._render_and_read(network_config=yaml.load(
            entry['yaml_v1']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())

    def testsimple_render_manual(self):
        """Test rendering of 'manual' for 'type' and 'control'.

        'type: manual' in a subnet is odd, but it is the way that was used
        to declare that a network device should get a mtu set on it even
        if there were no addresses to configure.  Also strange is the fact
        that in order to apply that MTU the ifupdown device must be set
        to 'auto', or the MTU would not be set."""
        entry = NETWORK_CONFIGS['manual']
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
            ('post-up route add -net 10.0.0.0/12 gw '
             '172.23.31.1 metric 0 || true'),
            ('pre-down route del -net 10.0.0.0/12 gw '
             '172.23.31.1 metric 0 || true'),
            ('post-up route add -net 192.168.2.0/16 gw '
             '172.23.31.1 metric 0 || true'),
            ('pre-down route del -net 192.168.2.0/16 gw '
             '172.23.31.1 metric 0 || true'),
            ('post-up route add -net 10.0.200.0/16 gw '
             '172.23.31.1 metric 1 || true'),
            ('pre-down route del -net 10.0.200.0/16 gw '
             '172.23.31.1 metric 1 || true'),
        ]
        found = files['/etc/network/interfaces'].splitlines()

        self.assertEqual(
            expected, [line for line in found if line])

    def test_ipv6_static_routes(self):
        # as reported in bug 1818669
        conf = [
            {'name': 'eno3', 'type': 'physical',
             'subnets': [{
                 'address': 'fd00::12/64',
                 'dns_nameservers': ['fd00:2::15'],
                 'gateway': 'fd00::1',
                 'ipv6': True,
                 'type': 'static',
                 'routes': [{'netmask': '32',
                             'network': 'fd00:12::',
                             'gateway': 'fd00::2'},
                            {'network': 'fd00:14::',
                             'gateway': 'fd00::3'},
                            {'destination': 'fe00:14::/48',
                             'gateway': 'fe00::4',
                             'metric': 500},
                            {'gateway': '192.168.23.1',
                             'metric': 999,
                             'netmask': 24,
                             'network': '192.168.23.0'},
                            {'destination': '10.23.23.0/24',
                             'gateway': '10.23.23.2',
                             'metric': 300}]}]},
        ]

        files = self._render_and_read(
            network_config={'config': conf, 'version': 1})
        expected = [
            'auto lo',
            'iface lo inet loopback',
            'auto eno3',
            'iface eno3 inet6 static',
            '    address fd00::12/64',
            '    dns-nameservers fd00:2::15',
            '    gateway fd00::1',
            ('    post-up route add -A inet6 fd00:12::/32 gw '
             'fd00::2 || true'),
            ('    pre-down route del -A inet6 fd00:12::/32 gw '
             'fd00::2 || true'),
            ('    post-up route add -A inet6 fd00:14::/64 gw '
             'fd00::3 || true'),
            ('    pre-down route del -A inet6 fd00:14::/64 gw '
             'fd00::3 || true'),
            ('    post-up route add -A inet6 fe00:14::/48 gw '
             'fe00::4 metric 500 || true'),
            ('    pre-down route del -A inet6 fe00:14::/48 gw '
             'fe00::4 metric 500 || true'),
            ('    post-up route add -net 192.168.23.0/24 gw '
             '192.168.23.1 metric 999 || true'),
            ('    pre-down route del -net 192.168.23.0/24 gw '
             '192.168.23.1 metric 999 || true'),
            ('    post-up route add -net 10.23.23.0/24 gw '
             '10.23.23.2 metric 300 || true'),
            ('    pre-down route del -net 10.23.23.0/24 gw '
             '10.23.23.2 metric 300 || true'),

        ]
        found = files['/etc/network/interfaces'].splitlines()

        self.assertEqual(
            expected, [line for line in found if line])

    def testsimple_render_bond(self):
        entry = NETWORK_CONFIGS['bond']
        files = self._render_and_read(network_config=yaml.load(entry['yaml']))
        self.assertEqual(
            entry['expected_eni'].splitlines(),
            files['/etc/network/interfaces'].splitlines())


class TestNetRenderers(CiTestCase):
    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_eni_and_sysconfig_available(self, m_eni_avail, m_sysc_avail):
        m_eni_avail.return_value = True
        m_sysc_avail.return_value = True
        found = renderers.search(priority=['sysconfig', 'eni'], first=False)
        names = [f[0] for f in found]
        self.assertEqual(['sysconfig', 'eni'], names)

    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_search_returns_empty_on_none(self, m_eni_avail):
        m_eni_avail.return_value = False
        found = renderers.search(priority=['eni'], first=False)
        self.assertEqual([], found)

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_first_in_priority(self, m_eni_avail, m_sysc_avail):
        # available should only be called until one is found.
        m_eni_avail.return_value = True
        m_sysc_avail.side_effect = Exception("Should not call me")
        found = renderers.search(priority=['eni', 'sysconfig'], first=True)
        self.assertEqual(['eni'], [found[0]])

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_select_positive(self, m_eni_avail, m_sysc_avail):
        m_eni_avail.return_value = True
        m_sysc_avail.return_value = False
        found = renderers.select(priority=['sysconfig', 'eni'])
        self.assertEqual('eni', found[0])

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_select_none_found_raises(self, m_eni_avail, m_sysc_avail):
        # if select finds nothing, should raise exception.
        m_eni_avail.return_value = False
        m_sysc_avail.return_value = False

        self.assertRaises(net.RendererNotFoundError, renderers.select,
                          priority=['sysconfig', 'eni'])

    @mock.patch("cloudinit.net.renderers.netplan.available")
    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.sysconfig.available_sysconfig")
    @mock.patch("cloudinit.net.renderers.sysconfig.available_nm")
    @mock.patch("cloudinit.net.renderers.eni.available")
    @mock.patch("cloudinit.net.renderers.sysconfig.util.get_linux_distro")
    def test_sysconfig_selected_on_sysconfig_enabled_distros(self, m_distro,
                                                             m_eni, m_sys_nm,
                                                             m_sys_scfg,
                                                             m_sys_avail,
                                                             m_netplan):
        """sysconfig only selected on specific distros (rhel/sles)."""

        # Ubuntu with Network-Manager installed
        m_eni.return_value = False        # no ifupdown (ifquery)
        m_sys_scfg.return_value = False   # no sysconfig/ifup/ifdown
        m_sys_nm.return_value = True      # network-manager is installed
        m_netplan.return_value = True     # netplan is installed
        m_sys_avail.return_value = False  # no sysconfig on Ubuntu
        m_distro.return_value = ('ubuntu', None, None)
        self.assertEqual('netplan', renderers.select(priority=None)[0])

        # Centos with Network-Manager installed
        m_eni.return_value = False       # no ifupdown (ifquery)
        m_sys_scfg.return_value = False  # no sysconfig/ifup/ifdown
        m_sys_nm.return_value = True     # network-manager is installed
        m_netplan.return_value = False   # netplan is not installed
        m_sys_avail.return_value = True  # sysconfig is available on centos
        m_distro.return_value = ('centos', None, None)
        self.assertEqual('sysconfig', renderers.select(priority=None)[0])

        # OpenSuse with Network-Manager installed
        m_eni.return_value = False       # no ifupdown (ifquery)
        m_sys_scfg.return_value = False  # no sysconfig/ifup/ifdown
        m_sys_nm.return_value = True     # network-manager is installed
        m_netplan.return_value = False   # netplan is not installed
        m_sys_avail.return_value = True  # sysconfig is available on opensuse
        m_distro.return_value = ('opensuse', None, None)
        self.assertEqual('sysconfig', renderers.select(priority=None)[0])

    @mock.patch("cloudinit.net.sysconfig.available_sysconfig")
    @mock.patch("cloudinit.util.get_linux_distro")
    def test_sysconfig_available_uses_variant_mapping(self, m_distro, m_avail):
        m_avail.return_value = True
        distro_values = [
           ('opensuse', '', ''),
           ('opensuse-leap', '', ''),
           ('opensuse-tumbleweed', '', ''),
           ('sles', '', ''),
           ('centos', '', ''),
           ('fedora', '', ''),
           ('redhat', '', ''),
        ]
        for (distro_name, distro_version, flavor) in distro_values:
            m_distro.return_value = (distro_name, distro_version, flavor)
            if hasattr(util.system_info, "cache_clear"):
                util.system_info.cache_clear()
            result = sysconfig.available()
            self.assertTrue(result)


class TestGetInterfaces(CiTestCase):
    _data = {'bonds': ['bond1'],
             'bridges': ['bridge1'],
             'vlans': ['bond1.101'],
             'own_macs': ['enp0s1', 'enp0s2', 'bridge1-nic', 'bridge1',
                          'bond1.101', 'lo', 'eth1'],
             'macs': {'enp0s1': 'aa:aa:aa:aa:aa:01',
                      'enp0s2': 'aa:aa:aa:aa:aa:02',
                      'bond1': 'aa:aa:aa:aa:aa:01',
                      'bond1.101': 'aa:aa:aa:aa:aa:01',
                      'bridge1': 'aa:aa:aa:aa:aa:03',
                      'bridge1-nic': 'aa:aa:aa:aa:aa:03',
                      'lo': '00:00:00:00:00:00',
                      'greptap0': '00:00:00:00:00:00',
                      'eth1': 'aa:aa:aa:aa:aa:01',
                      'tun0': None},
             'drivers': {'enp0s1': 'virtio_net',
                         'enp0s2': 'e1000',
                         'bond1': None,
                         'bond1.101': None,
                         'bridge1': None,
                         'bridge1-nic': None,
                         'lo': None,
                         'greptap0': None,
                         'eth1': 'mlx4_core',
                         'tun0': None}}
    data = {}

    def _se_get_devicelist(self):
        return list(self.data['devices'])

    def _se_device_driver(self, name):
        return self.data['drivers'][name]

    def _se_device_devid(self, name):
        return '0x%s' % sorted(list(self.data['drivers'].keys())).index(name)

    def _se_get_interface_mac(self, name):
        return self.data['macs'][name]

    def _se_is_bridge(self, name):
        return name in self.data['bridges']

    def _se_is_vlan(self, name):
        return name in self.data['vlans']

    def _se_interface_has_own_mac(self, name):
        return name in self.data['own_macs']

    def _mock_setup(self):
        self.data = copy.deepcopy(self._data)
        self.data['devices'] = set(list(self.data['macs'].keys()))
        mocks = ('get_devicelist', 'get_interface_mac', 'is_bridge',
                 'interface_has_own_mac', 'is_vlan', 'device_driver',
                 'device_devid')
        self.mocks = {}
        for n in mocks:
            m = mock.patch('cloudinit.net.' + n,
                           side_effect=getattr(self, '_se_' + n))
            self.addCleanup(m.stop)
            self.mocks[n] = m.start()

    def test_gi_includes_duplicate_macs(self):
        self._mock_setup()
        ret = net.get_interfaces()

        self.assertIn('enp0s1', self._se_get_devicelist())
        self.assertIn('eth1', self._se_get_devicelist())
        found = [ent for ent in ret if 'aa:aa:aa:aa:aa:01' in ent]
        self.assertEqual(len(found), 2)

    def test_gi_excludes_any_without_mac_address(self):
        self._mock_setup()
        ret = net.get_interfaces()

        self.assertIn('tun0', self._se_get_devicelist())
        found = [ent for ent in ret if 'tun0' in ent]
        self.assertEqual(len(found), 0)

    def test_gi_excludes_stolen_macs(self):
        self._mock_setup()
        ret = net.get_interfaces()
        self.mocks['interface_has_own_mac'].assert_has_calls(
            [mock.call('enp0s1'), mock.call('bond1')], any_order=True)
        expected = [
            ('enp0s2', 'aa:aa:aa:aa:aa:02', 'e1000', '0x5'),
            ('enp0s1', 'aa:aa:aa:aa:aa:01', 'virtio_net', '0x4'),
            ('eth1', 'aa:aa:aa:aa:aa:01', 'mlx4_core', '0x6'),
            ('lo', '00:00:00:00:00:00', None, '0x8'),
            ('bridge1-nic', 'aa:aa:aa:aa:aa:03', None, '0x3'),
        ]
        self.assertEqual(sorted(expected), sorted(ret))

    def test_gi_excludes_bridges(self):
        self._mock_setup()
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a bridge.
        # then expect b1 is the only thing left.
        self.data['macs']['b1'] = 'aa:aa:aa:aa:aa:b1'
        self.data['drivers']['b1'] = None
        self.data['devices'].add('b1')
        self.data['bonds'] = []
        self.data['own_macs'] = self.data['devices']
        self.data['bridges'] = [f for f in self.data['devices'] if f != "b1"]
        ret = net.get_interfaces()
        self.assertEqual([('b1', 'aa:aa:aa:aa:aa:b1', None, '0x0')], ret)
        self.mocks['is_bridge'].assert_has_calls(
            [mock.call('bridge1'), mock.call('enp0s1'), mock.call('bond1'),
             mock.call('b1')],
            any_order=True)


class TestInterfaceHasOwnMac(CiTestCase):
    """Test interface_has_own_mac.  This is admittedly a bit whitebox."""

    @mock.patch('cloudinit.net.read_sys_net_int', return_value=None)
    def test_non_strict_with_no_addr_assign_type(self, m_read_sys_net_int):
        """If nic does not have addr_assign_type, it is not "stolen".

        SmartOS containers do not provide the addr_assign_type in /sys.

            $ ( cd /sys/class/net/eth0/ && grep -r . *)
            address:90:b8:d0:20:e1:b0
            addr_len:6
            flags:0x1043
            ifindex:2
            mtu:1500
            tx_queue_len:1
            type:1
        """
        self.assertTrue(interface_has_own_mac("eth0"))

    @mock.patch('cloudinit.net.read_sys_net_int', return_value=None)
    def test_strict_with_no_addr_assign_type_raises(self, m_read_sys_net_int):
        with self.assertRaises(ValueError):
            interface_has_own_mac("eth0", True)

    @mock.patch('cloudinit.net.read_sys_net_int')
    def test_expected_values(self, m_read_sys_net_int):
        msg = "address_assign_type=%d said to not have own mac"
        for address_assign_type in (0, 1, 3):
            m_read_sys_net_int.return_value = address_assign_type
            self.assertTrue(
                interface_has_own_mac("eth0", msg % address_assign_type))

        m_read_sys_net_int.return_value = 2
        self.assertFalse(interface_has_own_mac("eth0"))


class TestGetInterfacesByMac(CiTestCase):
    _data = {'bonds': ['bond1'],
             'bridges': ['bridge1'],
             'vlans': ['bond1.101'],
             'own_macs': ['enp0s1', 'enp0s2', 'bridge1-nic', 'bridge1',
                          'bond1.101', 'lo'],
             'macs': {'enp0s1': 'aa:aa:aa:aa:aa:01',
                      'enp0s2': 'aa:aa:aa:aa:aa:02',
                      'bond1': 'aa:aa:aa:aa:aa:01',
                      'bond1.101': 'aa:aa:aa:aa:aa:01',
                      'bridge1': 'aa:aa:aa:aa:aa:03',
                      'bridge1-nic': 'aa:aa:aa:aa:aa:03',
                      'lo': '00:00:00:00:00:00',
                      'greptap0': '00:00:00:00:00:00',
                      'tun0': None}}
    data = {}

    def _se_get_devicelist(self):
        return list(self.data['devices'])

    def _se_get_interface_mac(self, name):
        return self.data['macs'][name]

    def _se_is_bridge(self, name):
        return name in self.data['bridges']

    def _se_is_vlan(self, name):
        return name in self.data['vlans']

    def _se_interface_has_own_mac(self, name):
        return name in self.data['own_macs']

    def _se_get_ib_interface_hwaddr(self, name, ethernet_format):
        ib_hwaddr = self.data.get('ib_hwaddr', {})
        return ib_hwaddr.get(name, {}).get(ethernet_format)

    def _mock_setup(self):
        self.data = copy.deepcopy(self._data)
        self.data['devices'] = set(list(self.data['macs'].keys()))
        mocks = ('get_devicelist', 'get_interface_mac', 'is_bridge',
                 'interface_has_own_mac', 'is_vlan', 'get_ib_interface_hwaddr')
        self.mocks = {}
        for n in mocks:
            m = mock.patch('cloudinit.net.' + n,
                           side_effect=getattr(self, '_se_' + n))
            self.addCleanup(m.stop)
            self.mocks[n] = m.start()

    def test_raise_exception_on_duplicate_macs(self):
        self._mock_setup()
        self.data['macs']['bridge1-nic'] = self.data['macs']['enp0s1']
        self.assertRaises(RuntimeError, net.get_interfaces_by_mac)

    def test_excludes_any_without_mac_address(self):
        self._mock_setup()
        ret = net.get_interfaces_by_mac()
        self.assertIn('tun0', self._se_get_devicelist())
        self.assertNotIn('tun0', ret.values())

    def test_excludes_stolen_macs(self):
        self._mock_setup()
        ret = net.get_interfaces_by_mac()
        self.mocks['interface_has_own_mac'].assert_has_calls(
            [mock.call('enp0s1'), mock.call('bond1')], any_order=True)
        self.assertEqual(
            {'aa:aa:aa:aa:aa:01': 'enp0s1', 'aa:aa:aa:aa:aa:02': 'enp0s2',
             'aa:aa:aa:aa:aa:03': 'bridge1-nic', '00:00:00:00:00:00': 'lo'},
            ret)

    def test_excludes_bridges(self):
        self._mock_setup()
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a bridge.
        # then expect b1 is the only thing left.
        self.data['macs']['b1'] = 'aa:aa:aa:aa:aa:b1'
        self.data['devices'].add('b1')
        self.data['bonds'] = []
        self.data['own_macs'] = self.data['devices']
        self.data['bridges'] = [f for f in self.data['devices'] if f != "b1"]
        ret = net.get_interfaces_by_mac()
        self.assertEqual({'aa:aa:aa:aa:aa:b1': 'b1'}, ret)
        self.mocks['is_bridge'].assert_has_calls(
            [mock.call('bridge1'), mock.call('enp0s1'), mock.call('bond1'),
             mock.call('b1')],
            any_order=True)

    def test_excludes_vlans(self):
        self._mock_setup()
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a vlan.
        # then expect b1 is the only thing left.
        self.data['macs']['b1'] = 'aa:aa:aa:aa:aa:b1'
        self.data['devices'].add('b1')
        self.data['bonds'] = []
        self.data['bridges'] = []
        self.data['own_macs'] = self.data['devices']
        self.data['vlans'] = [f for f in self.data['devices'] if f != "b1"]
        ret = net.get_interfaces_by_mac()
        self.assertEqual({'aa:aa:aa:aa:aa:b1': 'b1'}, ret)
        self.mocks['is_vlan'].assert_has_calls(
            [mock.call('bridge1'), mock.call('enp0s1'), mock.call('bond1'),
             mock.call('b1')],
            any_order=True)

    def test_duplicates_of_empty_mac_are_ok(self):
        """Duplicate macs of 00:00:00:00:00:00 should be skipped."""
        self._mock_setup()
        empty_mac = "00:00:00:00:00:00"
        addnics = ('greptap1', 'lo', 'greptap2')
        self.data['macs'].update(dict((k, empty_mac) for k in addnics))
        self.data['devices'].update(set(addnics))
        self.data['own_macs'].extend(list(addnics))
        ret = net.get_interfaces_by_mac()
        self.assertEqual('lo', ret[empty_mac])

    def test_skip_all_zeros(self):
        """Any mac of 00:... should be skipped."""
        self._mock_setup()
        emac1, emac2, emac4, emac6 = (
            '00', '00:00', '00:00:00:00', '00:00:00:00:00:00')
        addnics = {'empty1': emac1, 'emac2a': emac2, 'emac2b': emac2,
                   'emac4': emac4, 'emac6': emac6}
        self.data['macs'].update(addnics)
        self.data['devices'].update(set(addnics))
        self.data['own_macs'].extend(addnics.keys())
        ret = net.get_interfaces_by_mac()
        self.assertEqual('lo', ret['00:00:00:00:00:00'])

    def test_ib(self):
        ib_addr = '80:00:00:28:fe:80:00:00:00:00:00:00:00:11:22:03:00:33:44:56'
        ib_addr_eth_format = '00:11:22:33:44:56'
        self._mock_setup()
        self.data['devices'] = ['enp0s1', 'ib0']
        self.data['own_macs'].append('ib0')
        self.data['macs']['ib0'] = ib_addr
        self.data['ib_hwaddr'] = {'ib0': {True: ib_addr_eth_format,
                                          False: ib_addr}}
        result = net.get_interfaces_by_mac()
        expected = {'aa:aa:aa:aa:aa:01': 'enp0s1',
                    ib_addr_eth_format: 'ib0', ib_addr: 'ib0'}
        self.assertEqual(expected, result)


class TestInterfacesSorting(CiTestCase):

    def test_natural_order(self):
        data = ['ens5', 'ens6', 'ens3', 'ens20', 'ens13', 'ens2']
        self.assertEqual(
            sorted(data, key=natural_sort_key),
            ['ens2', 'ens3', 'ens5', 'ens6', 'ens13', 'ens20'])
        data2 = ['enp2s0', 'enp2s3', 'enp0s3', 'enp0s13', 'enp0s8', 'enp1s2']
        self.assertEqual(
            sorted(data2, key=natural_sort_key),
            ['enp0s3', 'enp0s8', 'enp0s13', 'enp1s2', 'enp2s0', 'enp2s3'])


class TestGetIBHwaddrsByInterface(CiTestCase):

    _ib_addr = '80:00:00:28:fe:80:00:00:00:00:00:00:00:11:22:03:00:33:44:56'
    _ib_addr_eth_format = '00:11:22:33:44:56'
    _data = {'devices': ['enp0s1', 'enp0s2', 'bond1', 'bridge1',
                         'bridge1-nic', 'tun0', 'ib0'],
             'bonds': ['bond1'],
             'bridges': ['bridge1'],
             'own_macs': ['enp0s1', 'enp0s2', 'bridge1-nic', 'bridge1', 'ib0'],
             'macs': {'enp0s1': 'aa:aa:aa:aa:aa:01',
                      'enp0s2': 'aa:aa:aa:aa:aa:02',
                      'bond1': 'aa:aa:aa:aa:aa:01',
                      'bridge1': 'aa:aa:aa:aa:aa:03',
                      'bridge1-nic': 'aa:aa:aa:aa:aa:03',
                      'tun0': None,
                      'ib0': _ib_addr},
             'ib_hwaddr': {'ib0': {True: _ib_addr_eth_format,
                                   False: _ib_addr}}}
    data = {}

    def _mock_setup(self):
        self.data = copy.deepcopy(self._data)
        mocks = ('get_devicelist', 'get_interface_mac', 'is_bridge',
                 'interface_has_own_mac', 'get_ib_interface_hwaddr')
        self.mocks = {}
        for n in mocks:
            m = mock.patch('cloudinit.net.' + n,
                           side_effect=getattr(self, '_se_' + n))
            self.addCleanup(m.stop)
            self.mocks[n] = m.start()

    def _se_get_devicelist(self):
        return self.data['devices']

    def _se_get_interface_mac(self, name):
        return self.data['macs'][name]

    def _se_is_bridge(self, name):
        return name in self.data['bridges']

    def _se_interface_has_own_mac(self, name):
        return name in self.data['own_macs']

    def _se_get_ib_interface_hwaddr(self, name, ethernet_format):
        ib_hwaddr = self.data.get('ib_hwaddr', {})
        return ib_hwaddr.get(name, {}).get(ethernet_format)

    def test_ethernet(self):
        self._mock_setup()
        self.data['devices'].remove('ib0')
        result = net.get_ib_hwaddrs_by_interface()
        expected = {}
        self.assertEqual(expected, result)

    def test_ib(self):
        self._mock_setup()
        result = net.get_ib_hwaddrs_by_interface()
        expected = {'ib0': self._ib_addr}
        self.assertEqual(expected, result)


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()


class TestRenameInterfaces(CiTestCase):

    @mock.patch('cloudinit.util.subp')
    def test_rename_all(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'interface0', 'virtio_net', '0x3'),
            ('00:11:22:33:44:aa', 'interface2', 'virtio_net', '0x5'),
        ]
        current_info = {
            'ens3': {
                'downable': True,
                'device_id': '0x3',
                'driver': 'virtio_net',
                'mac': '00:11:22:33:44:55',
                'name': 'ens3',
                'up': False},
            'ens5': {
                'downable': True,
                'device_id': '0x5',
                'driver': 'virtio_net',
                'mac': '00:11:22:33:44:aa',
                'name': 'ens5',
                'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'ens3', 'name', 'interface0'],
                      capture=True),
            mock.call(['ip', 'link', 'set', 'ens5', 'name', 'interface2'],
                      capture=True),
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_no_driver_no_device_id(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'interface0', None, None),
            ('00:11:22:33:44:aa', 'interface1', None, None),
        ]
        current_info = {
            'eth0': {
                'downable': True,
                'device_id': None,
                'driver': None,
                'mac': '00:11:22:33:44:55',
                'name': 'eth0',
                'up': False},
            'eth1': {
                'downable': True,
                'device_id': None,
                'driver': None,
                'mac': '00:11:22:33:44:aa',
                'name': 'eth1',
                'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'eth0', 'name', 'interface0'],
                      capture=True),
            mock.call(['ip', 'link', 'set', 'eth1', 'name', 'interface1'],
                      capture=True),
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_all_bounce(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'interface0', 'virtio_net', '0x3'),
            ('00:11:22:33:44:aa', 'interface2', 'virtio_net', '0x5'),
        ]
        current_info = {
            'ens3': {
                'downable': True,
                'device_id': '0x3',
                'driver': 'virtio_net',
                'mac': '00:11:22:33:44:55',
                'name': 'ens3',
                'up': True},
            'ens5': {
                'downable': True,
                'device_id': '0x5',
                'driver': 'virtio_net',
                'mac': '00:11:22:33:44:aa',
                'name': 'ens5',
                'up': True},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'ens3', 'down'], capture=True),
            mock.call(['ip', 'link', 'set', 'ens3', 'name', 'interface0'],
                      capture=True),
            mock.call(['ip', 'link', 'set', 'ens5', 'down'], capture=True),
            mock.call(['ip', 'link', 'set', 'ens5', 'name', 'interface2'],
                      capture=True),
            mock.call(['ip', 'link', 'set', 'interface0', 'up'], capture=True),
            mock.call(['ip', 'link', 'set', 'interface2', 'up'], capture=True)
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_duplicate_macs(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'eth0', 'hv_netsvc', '0x3'),
            ('00:11:22:33:44:55', 'vf1', 'mlx4_core', '0x5'),
        ]
        current_info = {
            'eth0': {
                'downable': True,
                'device_id': '0x3',
                'driver': 'hv_netsvc',
                'mac': '00:11:22:33:44:55',
                'name': 'eth0',
                'up': False},
            'eth1': {
                'downable': True,
                'device_id': '0x5',
                'driver': 'mlx4_core',
                'mac': '00:11:22:33:44:55',
                'name': 'eth1',
                'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'eth1', 'name', 'vf1'],
                      capture=True),
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_duplicate_macs_driver_no_devid(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'eth0', 'hv_netsvc', None),
            ('00:11:22:33:44:55', 'vf1', 'mlx4_core', None),
        ]
        current_info = {
            'eth0': {
                'downable': True,
                'device_id': '0x3',
                'driver': 'hv_netsvc',
                'mac': '00:11:22:33:44:55',
                'name': 'eth0',
                'up': False},
            'eth1': {
                'downable': True,
                'device_id': '0x5',
                'driver': 'mlx4_core',
                'mac': '00:11:22:33:44:55',
                'name': 'eth1',
                'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'eth1', 'name', 'vf1'],
                      capture=True),
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_multi_mac_dups(self, mock_subp):
        renames = [
            ('00:11:22:33:44:55', 'eth0', 'hv_netsvc', '0x3'),
            ('00:11:22:33:44:55', 'vf1', 'mlx4_core', '0x5'),
            ('00:11:22:33:44:55', 'vf2', 'mlx4_core', '0x7'),
        ]
        current_info = {
            'eth0': {
                'downable': True,
                'device_id': '0x3',
                'driver': 'hv_netsvc',
                'mac': '00:11:22:33:44:55',
                'name': 'eth0',
                'up': False},
            'eth1': {
                'downable': True,
                'device_id': '0x5',
                'driver': 'mlx4_core',
                'mac': '00:11:22:33:44:55',
                'name': 'eth1',
                'up': False},
            'eth2': {
                'downable': True,
                'device_id': '0x7',
                'driver': 'mlx4_core',
                'mac': '00:11:22:33:44:55',
                'name': 'eth2',
                'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)
        print(mock_subp.call_args_list)
        mock_subp.assert_has_calls([
            mock.call(['ip', 'link', 'set', 'eth1', 'name', 'vf1'],
                      capture=True),
            mock.call(['ip', 'link', 'set', 'eth2', 'name', 'vf2'],
                      capture=True),
        ])

    @mock.patch('cloudinit.util.subp')
    def test_rename_macs_case_insensitive(self, mock_subp):
        """_rename_interfaces must support upper or lower case macs."""
        renames = [
            ('aa:aa:aa:aa:aa:aa', 'en0', None, None),
            ('BB:BB:BB:BB:BB:BB', 'en1', None, None),
            ('cc:cc:cc:cc:cc:cc', 'en2', None, None),
            ('DD:DD:DD:DD:DD:DD', 'en3', None, None),
        ]
        current_info = {
            'eth0': {'downable': True, 'mac': 'AA:AA:AA:AA:AA:AA',
                     'name': 'eth0', 'up': False},
            'eth1': {'downable': True, 'mac': 'bb:bb:bb:bb:bb:bb',
                     'name': 'eth1', 'up': False},
            'eth2': {'downable': True, 'mac': 'cc:cc:cc:cc:cc:cc',
                     'name': 'eth2', 'up': False},
            'eth3': {'downable': True, 'mac': 'DD:DD:DD:DD:DD:DD',
                     'name': 'eth3', 'up': False},
        }
        net._rename_interfaces(renames, current_info=current_info)

        expected = [
            mock.call(['ip', 'link', 'set', 'eth%d' % i, 'name', 'en%d' % i],
                      capture=True)
            for i in range(len(renames))]
        mock_subp.assert_has_calls(expected)


class TestNetworkState(CiTestCase):

    def test_bcast_addr(self):
        """Test mask_and_ipv4_to_bcast_addr proper execution."""
        bcast_addr = network_state.mask_and_ipv4_to_bcast_addr
        self.assertEqual("192.168.1.255",
                         bcast_addr("255.255.255.0", "192.168.1.1"))
        self.assertEqual("128.42.7.255",
                         bcast_addr("255.255.248.0", "128.42.5.4"))
        self.assertEqual("10.1.21.255",
                         bcast_addr("255.255.255.0", "10.1.21.4"))

# vi: ts=4 expandtab
