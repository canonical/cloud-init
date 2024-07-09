# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import base64
import copy
import gzip
import io
import json
import os
import re
import textwrap
from typing import Optional

import pytest
import yaml
from yaml.serializer import Serializer

from cloudinit import distros, net, subp, temp_utils, util
from cloudinit.net import (
    cmdline,
    eni,
    interface_has_own_mac,
    mask_and_ipv4_to_bcast_addr,
    natural_sort_key,
    netplan,
    network_manager,
    network_state,
    networkd,
    renderers,
    sysconfig,
)
from cloudinit.sources.helpers import openstack
from tests.unittests.helpers import (
    dir2dict,
    does_not_raise,
    mock,
    populate_dir,
)
from tests.unittests.net.network_configs import NETWORK_CONFIGS

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
    "name": "eth0",
    "type": "physical",
    "subnets": [
        {
            "broadcast": "192.168.122.255",
            "control": "manual",
            "gateway": "192.168.122.1",
            "dns_search": ["foo.com"],
            "type": "dhcp",
            "netmask": "255.255.255.0",
            "dns_nameservers": ["192.168.122.1"],
        }
    ],
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
    "name": "eno1",
    "type": "physical",
    "subnets": [
        {
            "control": "manual",
            "dns_nameservers": ["2001:67c:1562:8010::2:1"],
            "netmask": "64",
            "type": "dhcp6",
        }
    ],
}


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
    "name": "eth1",
    "type": "physical",
    "subnets": [
        {
            "broadcast": "10.0.0.255",
            "control": "manual",
            "gateway": "10.0.0.1",
            "dns_search": ["foo.com"],
            "type": "static",
            "netmask": "255.255.255.0",
            "dns_nameservers": ["10.0.1.1"],
            "address": "10.0.0.2",
        }
    ],
}

STATIC_CONTENT_2 = """
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

STATIC_CONTENT_3 = """
DEVICE='eth1'
PROTO='off'
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
        bond-lacp_rate: fast
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
        bond-lacp_rate: fast
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
        bond-lacp_rate: fast
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
            routes:
            -   to: default
                via: 10.101.11.254
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
                gratuitous-arp: 1
        bond1:
            interfaces:
            - ens4
            macaddress: 68:05:ca:64:d3:6d
            mtu: 9000
            parameters:
                gratuitous-arp: 2
        bond2:
            interfaces:
            - ens5
            macaddress: 68:05:ca:64:d3:6e
            mtu: 9000
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
        ens5:
            dhcp4: false
            dhcp6: false
            match:
                macaddress: 52:54:00:99:11:99
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
        "in_data": {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        }
                    ],
                    "ip_address": "172.19.1.34",
                    "dns_search": ["testweb.com"],
                    "dns_nameservers": ["172.19.0.13"],
                    "id": "network0",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        },
        "in_macs": {
            "fa:16:3e:ed:9a:59": "eth0",
        },
        "out_sysconfig_opensuse": [
            (
                "etc/sysconfig/network/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
STARTMODE=auto
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.13
nameserver 172.19.0.12
search testweb.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/85-persistent-net-cloud-init.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "out_sysconfig_rhel": [
            (
                "etc/sysconfig/network-scripts/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
DNS1=172.19.0.13
DOMAIN=testweb.com
GATEWAY=172.19.3.254
HWADDR=fa:16:3e:ed:9a:59
IPADDR=172.19.1.34
NETMASK=255.255.252.0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.13
nameserver 172.19.0.12
search testweb.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/70-persistent-net.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "expected_network_manager": [
            (
                "".join(
                    [
                        "etc/NetworkManager/system-connections",
                        "/cloud-init-eth0.nmconnection",
                    ]
                ),
                """
# Generated by cloud-init. Changes will be lost.

[connection]
id=cloud-init eth0
uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
autoconnect-priority=120
type=ethernet

[user]
org.freedesktop.NetworkManager.origin=cloud-init

[ethernet]
mac-address=FA:16:3E:ED:9A:59

[ipv4]
method=manual
may-fail=false
address1=172.19.1.34/22
route1=0.0.0.0/0,172.19.3.254
dns=172.19.0.13;
dns-search=testweb.com;

""".lstrip(),
            ),
        ],
    },
    {
        "in_data": {
            "services": [
                {
                    "type": "dns",
                    "address": "172.19.0.12",
                    "search": ["example1.com", "example2.com"],
                }
            ],
            "networks": [
                {
                    "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "eth0",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        }
                    ],
                    "ip_address": "172.19.1.34",
                    "dns_search": ["example3.com"],
                    "dns_nameservers": ["172.19.0.12"],
                    "id": "network0",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "physical",
                    "id": "eth0",
                },
            ],
        },
        "in_macs": {
            "fa:16:3e:ed:9a:59": "eth0",
        },
        "out_sysconfig_opensuse": [
            (
                "etc/sysconfig/network/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
STARTMODE=auto
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
search example3.com example1.com example2.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/85-persistent-net-cloud-init.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "out_sysconfig_rhel": [
            (
                "etc/sysconfig/network-scripts/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
DNS1=172.19.0.12
DOMAIN=example3.com
GATEWAY=172.19.3.254
HWADDR=fa:16:3e:ed:9a:59
IPADDR=172.19.1.34
NETMASK=255.255.252.0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
search example3.com example1.com example2.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/70-persistent-net.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "expected_network_manager": [
            (
                "".join(
                    [
                        "etc/NetworkManager/system-connections",
                        "/cloud-init-eth0.nmconnection",
                    ]
                ),
                """
# Generated by cloud-init. Changes will be lost.

[connection]
id=cloud-init eth0
uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
autoconnect-priority=120
type=ethernet

[user]
org.freedesktop.NetworkManager.origin=cloud-init

[ethernet]
mac-address=FA:16:3E:ED:9A:59

[ipv4]
method=manual
may-fail=false
address1=172.19.1.34/22
route1=0.0.0.0/0,172.19.3.254
dns=172.19.0.12;
dns-search=example3.com;

""".lstrip(),
            ),
        ],
    },
    {
        "in_data": {
            "services": [
                {
                    "type": "dns",
                    "address": "172.19.0.12",
                    "search": "example.com",
                }
            ],
            "networks": [
                {
                    "network_id": "public-ipv4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        }
                    ],
                    "ip_address": "172.19.1.34",
                    "id": "network0",
                },
                {
                    "network_id": "private-ipv4",
                    "type": "ipv4",
                    "netmask": "255.255.255.0",
                    "link": "tap1a81968a-79",
                    "routes": [],
                    "ip_address": "10.0.0.10",
                    "id": "network1",
                },
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        },
        "in_macs": {
            "fa:16:3e:ed:9a:59": "eth0",
        },
        "out_sysconfig_opensuse": [
            (
                "etc/sysconfig/network/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
IPADDR1=10.0.0.10
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
NETMASK1=255.255.255.0
STARTMODE=auto
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
search example.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/85-persistent-net-cloud-init.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "out_sysconfig_rhel": [
            (
                "etc/sysconfig/network-scripts/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
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
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
search example.com
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/70-persistent-net.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
    },
    {
        "in_data": {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "public-ipv4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        }
                    ],
                    "ip_address": "172.19.1.34",
                    "id": "network0",
                },
                {
                    "network_id": "public-ipv6-a",
                    "type": "ipv6",
                    "netmask": "",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "gateway": "2001:DB8::1",
                            "netmask": "::",
                            "network": "::",
                        }
                    ],
                    "ip_address": "2001:DB8::10",
                    "id": "network1",
                },
                {
                    "network_id": "public-ipv6-b",
                    "type": "ipv6",
                    "netmask": "64",
                    "link": "tap1a81968a-79",
                    "routes": [],
                    "ip_address": "2001:DB9::10",
                    "id": "network2",
                },
                {
                    "network_id": "public-ipv6-c",
                    "type": "ipv6",
                    "netmask": "64",
                    "link": "tap1a81968a-79",
                    "routes": [],
                    "ip_address": "2001:DB10::10",
                    "id": "network3",
                },
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        },
        "in_macs": {
            "fa:16:3e:ed:9a:59": "eth0",
        },
        "out_sysconfig_opensuse": [
            (
                "etc/sysconfig/network/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=static
IPADDR=172.19.1.34
IPADDR6=2001:DB8::10/64
IPADDR6_1=2001:DB9::10/64
IPADDR6_2=2001:DB10::10/64
LLADDR=fa:16:3e:ed:9a:59
NETMASK=255.255.252.0
STARTMODE=auto
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/85-persistent-net-cloud-init.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
        "out_sysconfig_rhel": [
            (
                "etc/sysconfig/network-scripts/ifcfg-eth0",
                """
# Created by cloud-init automatically, do not edit.
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
IPV6_AUTOCONF=no
IPV6_DEFAULTGW=2001:DB8::1
IPV6_FORCE_ACCEPT_RA=no
NETMASK=255.255.252.0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip(),
            ),
            (
                "etc/resolv.conf",
                """
; Created by cloud-init automatically, do not edit.
;
nameserver 172.19.0.12
""".lstrip(),
            ),
            (
                "etc/NetworkManager/conf.d/99-cloud-init.conf",
                """
# Created by cloud-init automatically, do not edit.
#
[main]
dns = none
""".lstrip(),
            ),
            (
                "etc/udev/rules.d/70-persistent-net.rules",
                "".join(
                    [
                        'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ',
                        'ATTR{address}=="fa:16:3e:ed:9a:59", NAME="eth0"\n',
                    ]
                ),
            ),
        ],
    },
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


CONFIG_V1_EXPLICIT_LOOPBACK = {
    "version": 1,
    "config": [
        {
            "name": "eth0",
            "type": "physical",
            "subnets": [{"control": "auto", "type": "dhcp"}],
        },
        {
            "name": "lo",
            "type": "loopback",
            "subnets": [{"control": "auto", "type": "loopback"}],
        },
    ],
}


CONFIG_V1_SIMPLE_SUBNET = {
    "version": 1,
    "config": [
        {
            "mac_address": "52:54:00:12:34:00",
            "name": "interface0",
            "subnets": [
                {
                    "address": "10.0.2.15",
                    "gateway": "10.0.2.2",
                    "netmask": "255.255.255.0",
                    "type": "static",
                }
            ],
            "type": "physical",
        }
    ],
}

CONFIG_V1_MULTI_IFACE = {
    "version": 1,
    "config": [
        {
            "type": "physical",
            "mtu": 1500,
            "subnets": [
                {
                    "type": "static",
                    "netmask": "255.255.240.0",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "51.68.80.1",
                        }
                    ],
                    "address": "51.68.89.122",
                    "ipv4": True,
                }
            ],
            "mac_address": "fa:16:3e:25:b4:59",
            "name": "eth0",
        },
        {
            "type": "physical",
            "mtu": 9000,
            "subnets": [{"type": "dhcp4"}],
            "mac_address": "fa:16:3e:b1:ca:29",
            "name": "eth1",
        },
    ],
}

DEFAULT_DEV_ATTRS = {
    "eth1000": {
        "bridge": False,
        "carrier": False,
        "dormant": False,
        "operstate": "down",
        "address": "07-1c-c6-75-a4-be",
        "device/driver": None,
        "device/device": None,
        "name_assign_type": "4",
        "addr_assign_type": "0",
        "uevent": "",
        "type": "32",
    }
}


def _setup_test(
    tmp_dir,
    mock_get_devicelist,
    mock_read_sys_net,
    mock_sys_dev_path,
    dev_attrs=None,
):
    if not dev_attrs:
        dev_attrs = DEFAULT_DEV_ATTRS

    mock_get_devicelist.return_value = dev_attrs.keys()

    def fake_read(
        devname,
        path,
        translate=None,
        on_enoent=None,
        on_keyerror=None,
        on_einval=None,
    ):
        return dev_attrs[devname][path]

    mock_read_sys_net.side_effect = fake_read

    def sys_dev_path(devname, path=""):
        return tmp_dir + "/" + devname + "/" + path

    for dev in dev_attrs:
        os.makedirs(os.path.join(tmp_dir, dev))
        with open(os.path.join(tmp_dir, dev, "operstate"), "w") as fh:
            fh.write(dev_attrs[dev]["operstate"])
        os.makedirs(os.path.join(tmp_dir, dev, "device"))
        for key in ["device/driver"]:
            if key in dev_attrs[dev] and dev_attrs[dev][key]:
                target = dev_attrs[dev][key]
                link = os.path.join(tmp_dir, dev, key)
                print("symlink %s -> %s" % (link, target))
                os.symlink(target, link)

    mock_sys_dev_path.side_effect = sys_dev_path


class TestGenerateFallbackConfig:
    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmpdir_factory):
        mocker.patch(
            "cloudinit.util.get_cmdline",
            return_value="root=/dev/sda1",
        )
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_device_driver_v2(
        self, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
    ):
        """Network configuration for generate_fallback_config is version 2."""
        devices = {
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": "4",
            },
            "eth1": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "mlx4_core",
                "device/device": "0x7",
                "name_assign_type": "4",
            },
        }

        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )

        network_cfg = net.generate_fallback_config(config_driver=True)
        expected = {
            "ethernets": {
                "eth0": {
                    "dhcp4": True,
                    "dhcp6": True,
                    "set-name": "eth0",
                    "match": {
                        "macaddress": "00:11:22:33:44:55",
                        "driver": "hv_netvsc",
                    },
                }
            },
            "version": 2,
        }
        assert expected == network_cfg

    @mock.patch("cloudinit.net.openvswitch_is_installed", return_value=False)
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_device_driver(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        _ovs_is_installed,
    ):
        devices = {
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": "4",
                "addr_assign_type": "0",
                "uevent": "",
                "type": "32",
            },
            "eth1": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:56",
                "device/driver": "mlx4_core",
                "device/device": "0x7",
                "name_assign_type": "4",
                "addr_assign_type": "0",
                "uevent": "",
                "type": "32",
            },
        }

        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )

        network_cfg = net.generate_fallback_config(config_driver=True)
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        # don't set rulepath so eni writes them
        renderer = eni.Renderer(
            {"eni_path": "interfaces", "netrules_path": "netrules"}
        )
        renderer.render_network_state(ns, target=render_dir)

        assert os.path.exists(os.path.join(render_dir, "interfaces"))
        with open(os.path.join(render_dir, "interfaces")) as fh:
            contents = fh.read()
        print(contents)
        expected = """
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp

# control-alias eth0
iface eth0 inet6 dhcp
"""
        assert expected.lstrip() == contents.lstrip()

        assert os.path.exists(os.path.join(render_dir, "netrules"))
        with open(os.path.join(render_dir, "netrules")) as fh:
            contents = fh.read()
        print(contents)
        expected_rule = [
            'SUBSYSTEM=="net"',
            'ACTION=="add"',
            'DRIVERS=="hv_netvsc"',
            'ATTR{address}=="00:11:22:33:44:55"',
            'NAME="eth0"',
        ]
        assert ", ".join(expected_rule) + "\n" == contents.lstrip()

    @mock.patch("cloudinit.net.openvswitch_is_installed", return_value=False)
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_hv_netvsc_vf_filter(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        _ovs_installed,
    ):
        devices = {
            "eth1": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": "4",
                "addr_assign_type": "0",
                "uevent": "",
                "type": "32",
            },
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "mlx4_core",
                "device/device": "0x7",
                "name_assign_type": "4",
                "addr_assign_type": "0",
                "uevent": "",
                "type": "32",
            },
        }

        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )

        network_cfg = net.generate_fallback_config(config_driver=True)
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        # don't set rulepath so eni writes them
        renderer = eni.Renderer(
            {"eni_path": "interfaces", "netrules_path": "netrules"}
        )
        renderer.render_network_state(ns, target=render_dir)

        assert os.path.exists(os.path.join(render_dir, "interfaces"))
        with open(os.path.join(render_dir, "interfaces")) as fh:
            contents = fh.read()
        print(contents)
        expected = """
auto lo
iface lo inet loopback

auto eth1
iface eth1 inet dhcp

# control-alias eth1
iface eth1 inet6 dhcp
"""
        assert expected.lstrip() == contents.lstrip()

        assert os.path.exists(os.path.join(render_dir, "netrules"))
        with open(os.path.join(render_dir, "netrules")) as fh:
            contents = fh.read()
        print(contents)
        expected_rule = [
            'SUBSYSTEM=="net"',
            'ACTION=="add"',
            'DRIVERS=="hv_netvsc"',
            'ATTR{address}=="00:11:22:33:44:55"',
            'NAME="eth1"',
        ]
        assert ", ".join(expected_rule) + "\n" == contents.lstrip()

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("cloudinit.util.udevadm_settle")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_unstable_names(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        mock_settle,
        m_get_cmdline,
    ):
        """verify that udevadm settle is called when we find unstable names"""
        devices = {
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": False,
            },
            "ens4": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "mlx4_core",
                "device/device": "0x7",
                "name_assign_type": "4",
            },
        }

        m_get_cmdline.return_value = ""
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )
        net.generate_fallback_config(config_driver=True)
        assert 1 == mock_settle.call_count

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("cloudinit.util.udevadm_settle")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_unstable_names_disabled(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        mock_settle,
        m_get_cmdline,
    ):
        """verify udevadm settle not called when cmdline has net.ifnames=0"""
        devices = {
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": False,
            },
            "ens4": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "00:11:22:33:44:55",
                "device/driver": "mlx4_core",
                "device/device": "0x7",
                "name_assign_type": "4",
            },
        }

        m_get_cmdline.return_value = "net.ifnames=0"
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )
        net.generate_fallback_config(config_driver=True)
        assert 0 == mock_settle.call_count


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestRhelSysConfigRendering:
    scripts_dir = "/etc/sysconfig/network-scripts"
    header = "# Created by cloud-init automatically, do not edit.\n#\n"

    expected_name = "expected_sysconfig_rhel"

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def _get_renderer(self):
        distro_cls = distros.fetch("rhel")
        return sysconfig.Renderer(
            config=distro_cls.renderer_configs.get("sysconfig")
        )

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
            """Attempt to load shell content, otherwise return as-is"""
            try:
                return util.load_shell_content(f)
            except ValueError:
                pass
            # route6- * files aren't shell content, but iproute2 params
            return f

        expected_d = dict(
            (os.path.join(self.scripts_dir, k), _try_load(v))
            for k, v in expected.items()
        )

        # only compare the files in scripts_dir
        scripts_found = dict(
            (k, _try_load(v))
            for k, v in found.items()
            if k.startswith(self.scripts_dir)
        )
        assert expected_d == scripts_found

    def _assert_headers(self, found):
        missing = [
            f
            for f in found
            if (
                f.startswith(self.scripts_dir)
                and not found[f].startswith(self.header)
            )
        ]
        if missing:
            raise AssertionError("Missing headers in: %s" % missing)

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        m_get_cmdline,
    ):
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)

        render_file = "etc/sysconfig/network-scripts/ifcfg-eth1000"
        with open(os.path.join(render_dir, render_file)) as fh:
            content = fh.read()
            expected_content = """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1000
DHCPV6C=yes
HWADDR=07-1c-c6-75-a4-be
IPV6INIT=yes
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
""".lstrip()
            assert expected_content == content

    def test_multiple_ipv4_default_gateways(self):
        """ValueError is raised when duplicate ipv4 gateways exist."""
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        },
                        {
                            "netmask": "0.0.0.0",  # A second default gateway
                            "network": "0.0.0.0",
                            "gateway": "172.20.3.254",
                        },
                    ],
                    "ip_address": "172.19.1.34",
                    "id": "network0",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        }
        macs = {"fa:16:3e:ed:9a:59": "eth0"}
        render_dir = self.tmp_dir()
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )
        renderer = self._get_renderer()
        with pytest.raises(ValueError):
            renderer.render_network_state(ns, target=render_dir)
        assert [] == os.listdir(render_dir)

    def test_multiple_ipv6_default_gateways(self):
        """ValueError is raised when duplicate ipv6 gateways exist."""
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "public-ipv6",
                    "type": "ipv6",
                    "netmask": "",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "gateway": "2001:DB8::1",
                            "netmask": "::",
                            "network": "::",
                        },
                        {
                            "gateway": "2001:DB9::1",
                            "netmask": "::",
                            "network": "::",
                        },
                    ],
                    "ip_address": "2001:DB8::10",
                    "id": "network1",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        }
        macs = {"fa:16:3e:ed:9a:59": "eth0"}
        render_dir = self.tmp_dir()
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )
        renderer = self._get_renderer()
        with pytest.raises(ValueError):
            renderer.render_network_state(ns, target=render_dir)
        assert [] == os.listdir(render_dir)

    def test_invalid_network_mask_ipv6(self):
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "public-ipv6",
                    "type": "ipv6",
                    "netmask": "",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "gateway": "2001:DB8::1",
                            "netmask": "ff:ff:ff:ff::",
                            "network": "2001:DB8:1::1",
                        },
                    ],
                    "ip_address": "2001:DB8::10",
                    "id": "network1",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        }
        macs = {"fa:16:3e:ed:9a:59": "eth0"}
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        with pytest.raises(ValueError):
            network_state.parse_net_config_data(network_cfg, skip_broken=False)

    def test_invalid_network_mask_ipv4(self):
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "public-ipv4",
                    "type": "ipv4",
                    "netmask": "",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "gateway": "172.20.0.1",
                            "netmask": "255.234.255.0",
                            "network": "172.19.0.0",
                        },
                    ],
                    "ip_address": "172.20.0.10",
                    "id": "network1",
                }
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        }
        macs = {"fa:16:3e:ed:9a:59": "eth0"}
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        with pytest.raises(ValueError):
            network_state.parse_net_config_data(network_cfg, skip_broken=False)

    def test_openstack_rendering_samples(self):
        for os_sample in OS_SAMPLES:
            render_dir = self.tmp_dir()
            ex_input = os_sample["in_data"]
            ex_mac_addrs = os_sample["in_macs"]
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs
            )
            ns = network_state.parse_net_config_data(
                network_cfg, skip_broken=False
            )
            renderer = self._get_renderer()
            # render a multiple times to simulate reboots
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            for fn, expected_content in os_sample.get(
                "out_sysconfig_rhel", []
            ):
                with open(os.path.join(render_dir, fn)) as fh:
                    assert expected_content == fh.read()

    def test_network_config_v1_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_SIMPLE_SUBNET)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = "/etc/sysconfig/network-scripts/"
        assert nspath + "ifcfg-lo" not in found.keys()
        expected = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=interface0
GATEWAY=10.0.2.2
HWADDR=52:54:00:12:34:00
IPADDR=10.0.2.15
NETMASK=255.255.255.0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        assert expected == found[nspath + "ifcfg-interface0"]
        # The configuration has no nameserver information make sure we
        # do not write the resolv.conf file
        respath = "/etc/resolv.conf"
        assert respath not in found.keys()

    def test_network_config_v1_multi_iface_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_MULTI_IFACE)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = "/etc/sysconfig/network-scripts/"
        assert nspath + "ifcfg-lo" not in found.keys()
        expected_i1 = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=none
DEFROUTE=yes
DEVICE=eth0
GATEWAY=51.68.80.1
HWADDR=fa:16:3e:25:b4:59
IPADDR=51.68.89.122
MTU=1500
NETMASK=255.255.240.0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        assert expected_i1 == found[nspath + "ifcfg-eth0"]
        expected_i2 = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth1
DHCLIENT_SET_DEFAULT_ROUTE=no
HWADDR=fa:16:3e:b1:ca:29
MTU=9000
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        assert expected_i2 == found[nspath + "ifcfg-eth1"]

    def test_config_with_explicit_loopback(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        # write an etc/resolv.conf and expect it to not be modified
        resolvconf = os.path.join(render_dir, "etc/resolv.conf")
        resolvconf_content = "# Original Content"
        util.write_file(resolvconf, resolvconf_content)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = "/etc/sysconfig/network-scripts/"
        assert nspath + "ifcfg-lo" not in found.keys()
        expected = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=dhcp
DEVICE=eth0
ONBOOT=yes
TYPE=Ethernet
USERCTL=no
"""
        assert expected == found[nspath + "ifcfg-eth0"]
        # a dhcp only config should not modify resolv.conf
        assert resolvconf_content == found["/etc/resolv.conf"]

    @pytest.mark.parametrize(
        "expected_name,yaml_version",
        [
            ("bond_v1", "yaml"),
            pytest.param(
                "bond_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="Bond MAC address not rendered"
                ),
            ),
            ("vlan_v1", "yaml"),
            ("vlan_v2", "yaml"),
            ("bridge", "yaml_v1"),
            ("bridge", "yaml_v2"),
            ("manual", "yaml"),
            ("small_v1", "yaml"),
            ("small_v2", "yaml"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("dhcpv6_accept_ra", "yaml_v1"),
            ("dhcpv6_accept_ra", "yaml_v2"),
            ("dhcpv6_reject_ra", "yaml_v1"),
            ("dhcpv6_reject_ra", "yaml_v2"),
            ("static6", "yaml_v1"),
            ("static6", "yaml_v2"),
            ("dhcpv6_stateless", "yaml"),
            ("dhcpv6_stateful", "yaml"),
            ("wakeonlan_disabled", "yaml_v2"),
            ("wakeonlan_enabled", "yaml_v2"),
            pytest.param(
                "v1-dns",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="sysconfig should render interface-level DNS"
                ),
            ),
            ("v2-dns", "yaml"),
            pytest.param(
                "large_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="Bond and Bridge MAC address not rendered"
                ),
            ),
        ],
    )
    def test_config(self, expected_name, yaml_version):
        entry = NETWORK_CONFIGS[expected_name]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_version])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_large_v1_config(self, caplog):
        entry = NETWORK_CONFIGS["large_v1"]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        assert (
            "Network config: ignoring eth0.101 device-level mtu"
            not in caplog.text
        )

    @pytest.mark.parametrize(
        "yaml_file,network_config",
        [
            ("yaml_v1", "v1_ipv4_and_ipv6_static"),
            ("yaml_v2", "v2_ipv4_and_ipv6_static"),
        ],
    )
    def test_ipv4_and_ipv6_static_config(
        self, yaml_file, network_config, caplog
    ):
        entry = NETWORK_CONFIGS[network_config]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_file])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        expected_msg = (
            "Network config: ignoring iface0 device-level mtu:8999"
            " because ipv4 subnet-level mtu:9000 provided."
        )
        if yaml_file == "yaml_v1":
            assert expected_msg in caplog.text

    def test_stattic6_from_json(self):
        net_json = {
            "services": [{"type": "dns", "address": "172.19.0.12"}],
            "networks": [
                {
                    "network_id": "dacd568d-5be6-4786-91fe-750c374b78b4",
                    "type": "ipv4",
                    "netmask": "255.255.252.0",
                    "link": "tap1a81968a-79",
                    "routes": [
                        {
                            "netmask": "0.0.0.0",
                            "network": "0.0.0.0",
                            "gateway": "172.19.3.254",
                        },
                        {
                            "netmask": "0.0.0.0",  # A second default gateway
                            "network": "0.0.0.0",
                            "gateway": "172.20.3.254",
                        },
                    ],
                    "ip_address": "172.19.1.34",
                    "id": "network0",
                },
                {
                    "network_id": "mgmt",
                    "netmask": "ffff:ffff:ffff:ffff::",
                    "link": "interface1",
                    "mode": "link-local",
                    "routes": [],
                    "ip_address": "fe80::c096:67ff:fe5c:6e84",
                    "type": "static6",
                    "id": "network1",
                    "services": [],
                    "accept-ra": "false",
                },
            ],
            "links": [
                {
                    "ethernet_mac_address": "fa:16:3e:ed:9a:59",
                    "mtu": None,
                    "type": "bridge",
                    "id": "tap1a81968a-79",
                    "vif_id": "1a81968a-797a-400f-8a80-567f997eb93f",
                },
            ],
        }
        macs = {"fa:16:3e:ed:9a:59": "eth0"}
        render_dir = self.tmp_dir()
        network_cfg = openstack.convert_net_json(net_json, known_macs=macs)
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )
        renderer = self._get_renderer()
        with pytest.raises(ValueError):
            renderer.render_network_state(ns, target=render_dir)
        assert [] == os.listdir(render_dir)

    def test_netplan_dhcp_false_disable_dhcp_in_state(self):
        """netplan config with dhcp[46]: False should not add dhcp in state"""
        net_config = yaml.safe_load(NETPLAN_DHCP_FALSE)
        ns = network_state.parse_net_config_data(net_config, skip_broken=False)

        dhcp_found = [
            snet
            for iface in ns.iter_interfaces()
            for snet in iface["subnets"]
            if "dhcp" in snet["type"]
        ]

        assert [] == dhcp_found

    def test_netplan_dhcp_false_no_dhcp_in_sysconfig(self):
        """netplan cfg with dhcp[46]: False should not have bootproto=dhcp"""

        entry = {
            "yaml": NETPLAN_DHCP_FALSE,
            "expected_sysconfig": {
                "ifcfg-ens3": textwrap.dedent(
                    """\
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
                   IPV6_AUTOCONF=no
                   IPV6_FORCE_ACCEPT_RA=no
                   IPV6_DEFAULTGW=2001:db8::1
                   NETMASK=255.255.255.0
                   ONBOOT=yes
                   TYPE=Ethernet
                   USERCTL=no
                   """
                ),
            },
        }

        found = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )
        self._compare_files_to_expected(entry["expected_sysconfig"], found)
        self._assert_headers(found)

    def test_from_v2_vlan_mtu(self):
        """verify mtu gets rendered on bond when source is netplan."""
        v2data = {
            "version": 2,
            "ethernets": {"eno1": {}},
            "vlans": {
                "eno1.1000": {
                    "addresses": ["192.6.1.9/24"],
                    "id": 1000,
                    "link": "eno1",
                    "mtu": 1495,
                }
            },
        }
        expected = {
            "ifcfg-eno1": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eno1
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
            "ifcfg-eno1.1000": textwrap.dedent(
                """\
                BOOTPROTO=none
                DEVICE=eno1.1000
                IPADDR=192.6.1.9
                MTU=1495
                NETMASK=255.255.255.0
                ONBOOT=yes
                PHYSDEV=eno1
                USERCTL=no
                VLAN=yes
                """
            ),
        }
        self._compare_files_to_expected(
            expected, self._render_and_read(network_config=v2data)
        )

    def test_from_v2_bond_mtu(self):
        """verify mtu gets rendered on bond when source is netplan."""
        v2data = {
            "version": 2,
            "bonds": {
                "bond0": {
                    "addresses": ["10.101.8.65/26"],
                    "interfaces": ["enp0s0", "enp0s1"],
                    "mtu": 1334,
                    "parameters": {},
                }
            },
        }
        expected = {
            "ifcfg-bond0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BONDING_SLAVE0=enp0s0
                BONDING_SLAVE1=enp0s1
                BOOTPROTO=none
                DEVICE=bond0
                IPADDR=10.101.8.65
                MTU=1334
                NETMASK=255.255.255.192
                ONBOOT=yes
                TYPE=Bond
                USERCTL=no
                """
            ),
            "ifcfg-enp0s0": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BOOTPROTO=none
                DEVICE=enp0s0
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Bond
                USERCTL=no
                """
            ),
            "ifcfg-enp0s1": textwrap.dedent(
                """\
                BONDING_MASTER=yes
                BOOTPROTO=none
                DEVICE=enp0s1
                MASTER=bond0
                ONBOOT=yes
                SLAVE=yes
                TYPE=Bond
                USERCTL=no
                """
            ),
        }
        self._compare_files_to_expected(
            expected, self._render_and_read(network_config=v2data)
        )

    def test_from_v2_route_metric(self):
        """verify route-metric gets rendered on nic when source is netplan."""
        overrides = {"route-metric": 100}
        v2base = {
            "version": 2,
            "ethernets": {
                "eno1": {
                    "dhcp4": True,
                    "match": {"macaddress": "07-1c-c6-75-a4-be"},
                }
            },
        }
        expected = {
            "ifcfg-eno1": textwrap.dedent(
                """\
                BOOTPROTO=dhcp
                DEVICE=eno1
                HWADDR=07-1c-c6-75-a4-be
                METRIC=100
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """
            ),
        }
        for dhcp_ver in ("dhcp4", "dhcp6"):
            v2data = copy.deepcopy(v2base)
            if dhcp_ver == "dhcp6":
                expected["ifcfg-eno1"] += "IPV6INIT=yes\nDHCPV6C=yes\n"
            v2data["ethernets"]["eno1"].update(
                {dhcp_ver: True, "{0}-overrides".format(dhcp_ver): overrides}
            )
            self._compare_files_to_expected(
                expected, self._render_and_read(network_config=v2data)
            )

    def test_from_v2_routes(self):
        """verify routes (including IPv6) get rendered using v2 config.

        LP: #1958506
        """
        v2_data = {
            "version": 2,
            "ethernets": {
                "eth0": {
                    "addresses": [
                        "10.54.2.19/21",
                        "2a00:1730:fff9:100::52/128",
                    ],
                    "gateway4": "10.54.0.1",
                    "gateway6": "2a00:1730:fff9:100::1",
                    "match": {"macaddress": "52:54:00:3f:fc:f7"},
                    "mtu": 1400,
                    "nameservers": {
                        "addresses": [
                            "10.52.1.1",
                            "10.52.1.71",
                            "2001:4860:4860::8888",
                            "2001:4860:4860::8844",
                        ]
                    },
                    "routes": [
                        {
                            "scope": "link",
                            "to": "10.54.0.1/32",
                            "via": "0.0.0.0",
                        },
                        {
                            "scope": "link",
                            "to": "0.0.0.0/0",
                            "via": "10.54.0.1",
                        },
                        {
                            "scope": "link",
                            "to": "2a00:1730:fff9:100::1/128",
                            "via": "::0",
                        },
                        {
                            "scope": "link",
                            "to": "::0/0",
                            "via": "2a00:1730:fff9:100::1",
                        },
                    ],
                    "set-name": "eth0",
                }
            },
        }

        expected = {
            "ifcfg-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                BOOTPROTO=none
                DEFROUTE=yes
                DEVICE=eth0
                DNS1=10.52.1.1
                DNS2=10.52.1.71
                DNS3=2001:4860:4860::8888
                GATEWAY=10.54.0.1
                HWADDR=52:54:00:3f:fc:f7
                IPADDR=10.54.2.19
                IPV6ADDR=2a00:1730:fff9:100::52/128
                IPV6INIT=yes
                IPV6_AUTOCONF=no
                IPV6_DEFAULTGW=2a00:1730:fff9:100::1
                IPV6_FORCE_ACCEPT_RA=no
                MTU=1400
                NETMASK=255.255.248.0
                ONBOOT=yes
                TYPE=Ethernet
                USERCTL=no
                """  # noqa: E501
            ),
            "route-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                ADDRESS0=10.54.0.1
                GATEWAY0=0.0.0.0
                NETMASK0=255.255.255.255
                """  # noqa: E501
            ),
            "route6-eth0": textwrap.dedent(
                """\
                # Created by cloud-init automatically, do not edit.
                #
                2a00:1730:fff9:100::1/128 via ::0  dev eth0
                ::0/0 via 2a00:1730:fff9:100::1  dev eth0
                """  # noqa: E501
            ),
        }

        found = self._render_and_read(network_config=v2_data)
        self._compare_files_to_expected(expected, found)
        self._assert_headers(found)

    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_iface_name_from_device_with_matching_mac_address(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
    ):
        devices = {
            "eth0": {
                "bridge": False,
                "carrier": False,
                "dormant": False,
                "operstate": "down",
                "address": "CF:D6:AF:48:E8:80",
                "device/driver": "hv_netvsc",
                "device/device": "0x3",
                "name_assign_type": "4",
                "addr_assign_type": "0",
                "uevent": "",
                "type": "32",
            },
        }

        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir,
            mock_get_devicelist,
            mock_read_sys_net,
            mock_sys_dev_path,
            dev_attrs=devices,
        )
        entry = NETWORK_CONFIGS["v2-dev-name-via-mac-lookup"]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestOpenSuseSysConfigRendering:

    scripts_dir = "/etc/sysconfig/network"
    header = "# Created by cloud-init automatically, do not edit.\n#\n"

    expected_name = "expected_sysconfig_opensuse"

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def _get_renderer(self):
        distro_cls = distros.fetch("opensuse")
        return sysconfig.Renderer(
            config=distro_cls.renderer_configs.get("sysconfig")
        )

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
        expected_d = dict(
            (os.path.join(self.scripts_dir, k), util.load_shell_content(v))
            for k, v in expected.items()
        )

        # only compare the files in scripts_dir
        scripts_found = dict(
            (k, util.load_shell_content(v))
            for k, v in found.items()
            if k.startswith(self.scripts_dir)
        )
        assert expected_d == scripts_found

    def _assert_headers(self, found):
        missing = [
            f
            for f in found
            if (
                f.startswith(self.scripts_dir)
                and not found[f].startswith(self.header)
            )
        ]
        if missing:
            raise AssertionError("Missing headers in: %s" % missing)

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        m_get_cmdline,
    ):
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)

        render_file = "etc/sysconfig/network/ifcfg-eth1000"
        with open(os.path.join(render_dir, render_file)) as fh:
            content = fh.read()
            expected_content = """
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=dhcp
DHCLIENT6_MODE=managed
LLADDR=07-1c-c6-75-a4-be
STARTMODE=auto
""".lstrip()
            assert expected_content == content

    # TODO(rjschwei): re-add tests once route writing is implemented.
    # See git history for removed commented tests

    def test_openstack_rendering_samples(self):
        for os_sample in OS_SAMPLES:
            render_dir = self.tmp_dir()
            ex_input = os_sample["in_data"]
            ex_mac_addrs = os_sample["in_macs"]
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs
            )
            ns = network_state.parse_net_config_data(
                network_cfg, skip_broken=False
            )
            renderer = self._get_renderer()
            # render a multiple times to simulate reboots
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            for fn, expected_content in os_sample.get(
                "out_sysconfig_opensuse", []
            ):
                with open(os.path.join(render_dir, fn)) as fh:
                    assert expected_content == fh.read()

    def test_network_config_v1_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_SIMPLE_SUBNET)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = "/etc/sysconfig/network/"
        assert nspath + "ifcfg-lo" not in found.keys()
        expected = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=static
IPADDR=10.0.2.15
LLADDR=52:54:00:12:34:00
NETMASK=255.255.255.0
STARTMODE=auto
"""
        assert expected == found[nspath + "ifcfg-interface0"]
        # The configuration has no nameserver information make sure we
        # do not write the resolv.conf file
        respath = "/etc/resolv.conf"
        assert respath not in found.keys()

    def test_config_with_explicit_loopback(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        # write an etc/resolv.conf and expect it to not be modified
        resolvconf = os.path.join(render_dir, "etc/resolv.conf")
        resolvconf_content = "# Original Content"
        util.write_file(resolvconf, resolvconf_content)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        nspath = "/etc/sysconfig/network/"
        assert nspath + "ifcfg-lo" not in found.keys()
        expected = """\
# Created by cloud-init automatically, do not edit.
#
BOOTPROTO=dhcp4
STARTMODE=auto
"""
        assert expected == found[nspath + "ifcfg-eth0"]
        # a dhcp only config should not modify resolv.conf
        assert resolvconf_content == found["/etc/resolv.conf"]

    @pytest.mark.parametrize(
        "expected_name,yaml_name",
        [
            ("bond_v1", "yaml"),
            pytest.param(
                "bond_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="Bond MAC address not rendered"
                ),
            ),
            ("vlan_v1", "yaml"),
            ("vlan_v2", "yaml"),
            ("bridge", "yaml_v1"),
            ("bridge", "yaml_v2"),
            ("manual", "yaml"),
            ("small_v1", "yaml"),
            ("small_suse_dhcp6", "yaml_v1"),
            ("small_suse_dhcp6", "yaml_v2"),
            ("small_v2", "yaml"),
            ("v1_ipv4_and_ipv6_static", "yaml_v1"),
            ("v2_ipv4_and_ipv6_static", "yaml_v2"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("ipv6_slaac", "yaml"),
            ("dhcpv6_stateless", "yaml"),
            ("wakeonlan_disabled", "yaml_v2"),
            ("wakeonlan_enabled", "yaml_v2"),
            ("v4_and_v6", "yaml_v1"),
            ("v4_and_v6", "yaml_v2"),
            ("v6_and_v4", "yaml"),
            ("v1-dns", "yaml"),
            ("v2-dns", "yaml"),
            pytest.param(
                "large_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="Bond and Bridge LLADDR not rendered"
                ),
            ),
        ],
    )
    def test_config(
        self,
        expected_name,
        yaml_name,
    ):
        entry = NETWORK_CONFIGS[expected_name]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_name])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)

    def test_large_v2_config(self, caplog):
        entry = NETWORK_CONFIGS["large_v1"]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )
        self._compare_files_to_expected(entry[self.expected_name], found)
        self._assert_headers(found)
        assert (
            "Network config: ignoring eth0.101 device-level mtu"
            not in caplog.text
        )


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestNetworkManagerRendering:
    scripts_dir = "/etc/NetworkManager/system-connections"
    conf_dir = "/etc/NetworkManager/conf.d"

    expected_name = "expected_network_manager"

    expected_conf_d = {
        "30-cloud-init-ip6-addr-gen-mode.conf": textwrap.dedent(
            """\
                # This is generated by cloud-init. Do not edit.
                #
                [.config]
                  enable=nm-version-min:1.40
                [connection.30-cloud-init-ip6-addr-gen-mode]
                  # Select EUI64 to be used if the profile does not specify it.
                  ipv6.addr-gen-mode=0

                """
        ),
    }

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir):
        self.tmp_dir = lambda: str(tmpdir)

    def _get_renderer(self):
        return network_manager.Renderer()

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

    def _compare_files_to_expected(
        self, expected_scripts, expected_conf, found
    ):
        conf_d = dict(
            (os.path.join(self.conf_dir, k), v)
            for k, v in expected_conf.items()
        )
        scripts_d = dict(
            (os.path.join(self.scripts_dir, k), v)
            for k, v in expected_scripts.items()
        )
        expected_d = {**conf_d, **scripts_d}

        assert expected_d == found

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        m_get_cmdline,
    ):
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)

        found = dir2dict(render_dir)
        self._compare_files_to_expected(
            {
                "cloud-init-eth1000.nmconnection": textwrap.dedent(
                    """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth1000
                uuid=8c517500-0c95-5308-9c8a-3092eebc44eb
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=07:1C:C6:75:A4:BE

                [ipv4]
                method=auto
                may-fail=true

                [ipv6]
                method=auto
                may-fail=true

                """
                ),
            },
            self.expected_conf_d,
            found,
        )

    def test_openstack_rendering_samples(self):
        for os_sample in OS_SAMPLES:
            render_dir = self.tmp_dir()
            ex_input = os_sample["in_data"]
            ex_mac_addrs = os_sample["in_macs"]
            network_cfg = openstack.convert_net_json(
                ex_input, known_macs=ex_mac_addrs
            )
            ns = network_state.parse_net_config_data(
                network_cfg, skip_broken=False
            )
            renderer = self._get_renderer()
            # render a multiple times to simulate reboots
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            renderer.render_network_state(ns, target=render_dir)
            for fn, expected_content in os_sample.get(self.expected_name, []):
                with open(os.path.join(render_dir, fn)) as fh:
                    assert expected_content == fh.read()

    def test_network_config_v1_samples(self):
        ns = network_state.parse_net_config_data(CONFIG_V1_SIMPLE_SUBNET)
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        self._compare_files_to_expected(
            {
                "cloud-init-interface0.nmconnection": textwrap.dedent(
                    """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init interface0
                uuid=8b6862ed-dbd6-5830-93f7-a91451c13828
                autoconnect-priority=120
                type=ethernet

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]
                mac-address=52:54:00:12:34:00

                [ipv4]
                method=manual
                may-fail=false
                address1=10.0.2.15/24
                gateway=10.0.2.2

                """
                )
            },
            self.expected_conf_d,
            found,
        )

    def test_config_with_explicit_loopback(self):
        render_dir = os.path.join(self.tmp_dir(), "render")
        os.makedirs(render_dir)
        ns = network_state.parse_net_config_data(CONFIG_V1_EXPLICIT_LOOPBACK)
        renderer = self._get_renderer()
        renderer.render_network_state(ns, target=render_dir)
        found = dir2dict(render_dir)
        self._compare_files_to_expected(
            {
                "cloud-init-eth0.nmconnection": textwrap.dedent(
                    """\
                # Generated by cloud-init. Changes will be lost.

                [connection]
                id=cloud-init eth0
                uuid=1dd9a779-d327-56e1-8454-c65e2556c12c
                autoconnect-priority=120
                type=ethernet
                interface-name=eth0

                [user]
                org.freedesktop.NetworkManager.origin=cloud-init

                [ethernet]

                [ipv4]
                method=auto
                may-fail=false

                """
                ),
            },
            self.expected_conf_d,
            found,
        )

    @pytest.mark.parametrize(
        "yaml_file,config",
        [
            ("yaml_v1", "v1_ipv4_and_ipv6_static"),
            ("yaml_v2", "v2_ipv4_and_ipv6_static"),
        ],
    )
    def test_ipv4_and_ipv6_static_config(self, yaml_file, config, caplog):
        entry = NETWORK_CONFIGS[config]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_file])
        )
        self._compare_files_to_expected(
            entry[self.expected_name], self.expected_conf_d, found
        )
        expected_msg = (
            "Network config: ignoring iface0 device-level mtu:8999"
            " because ipv4 subnet-level mtu:9000 provided."
        )
        if yaml_file == "yaml_v1":
            assert expected_msg in caplog.text

    @pytest.mark.parametrize(
        "expected_name,yaml_name",
        [
            ("bond_v1", "yaml"),
            pytest.param(
                "bond_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="mii-monitor-interval not rendered."
                ),
            ),
            ("vlan_v1", "yaml"),
            ("vlan_v2", "yaml"),
            ("bridge", "yaml_v1"),
            ("bridge", "yaml_v2"),
            ("manual", "yaml"),
            ("small_v1", "yaml"),
            ("small_v2", "yaml"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("ipv6_slaac", "yaml"),
            ("dhcpv6_stateless", "yaml"),
            ("wakeonlan_disabled", "yaml_v2"),
            ("wakeonlan_enabled", "yaml_v2"),
            ("v4_and_v6", "yaml_v1"),
            ("v4_and_v6", "yaml_v2"),
            ("v6_and_v4", "yaml"),
            ("v1-dns", "yaml"),
            ("v2-mixed-routes", "yaml"),
            ("v2-dns", "yaml"),
            ("v2-dns-no-if-ips", "yaml"),
            ("v2-dns-no-dhcp", "yaml"),
            ("v2-route-no-gateway", "yaml"),
            pytest.param(
                "large_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason=(
                        "Bridge MAC and bond miimon not rendered. "
                        "Bond DNS not rendered. "
                        "DNS not rendered when DHCP is enabled."
                    ),
                ),
            ),
        ],
    )
    def test_config(self, expected_name, yaml_name):
        entry = NETWORK_CONFIGS[expected_name]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_name])
        )
        self._compare_files_to_expected(
            entry[self.expected_name], self.expected_conf_d, found
        )

    def test_large_v1_config(self, caplog):
        entry = NETWORK_CONFIGS["large_v1"]
        found = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )
        self._compare_files_to_expected(
            entry[self.expected_name], self.expected_conf_d, found
        )
        assert (
            "Network config: ignoring eth0.101 device-level mtu"
            not in caplog.text
        )


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestEniNetRendering:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_default_generation(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        m_get_cmdline,
    ):
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        renderer = eni.Renderer(
            {"eni_path": "interfaces", "netrules_path": None}
        )
        renderer.render_network_state(ns, target=render_dir)

        assert os.path.exists(os.path.join(render_dir, "interfaces"))
        with open(os.path.join(render_dir, "interfaces")) as fh:
            contents = fh.read()

        expected = """
auto lo
iface lo inet loopback

auto eth1000
iface eth1000 inet dhcp

# control-alias eth1000
iface eth1000 inet6 dhcp
"""
        assert expected.lstrip() == contents.lstrip()

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
        assert expected == dir2dict(tmp_dir)["/etc/network/interfaces"]

    def test_v2_route_metric_to_eni(self):
        """Network v2 route-metric overrides are preserved in eni output"""
        tmp_dir = self.tmp_dir()
        renderer = eni.Renderer()
        expected_tmpl = textwrap.dedent(
            """\
            auto lo
            iface lo inet loopback

            auto eth0
            iface eth0 inet{suffix} dhcp
                metric 100
            """
        )
        for dhcp_ver in ("dhcp4", "dhcp6"):
            suffix = "6" if dhcp_ver == "dhcp6" else ""
            dhcp_cfg = {
                dhcp_ver: True,
                "{ver}-overrides".format(ver=dhcp_ver): {"route-metric": 100},
            }
            v2_input = {"version": 2, "ethernets": {"eth0": dhcp_cfg}}
            ns = network_state.parse_net_config_data(v2_input)
            renderer.render_network_state(ns, target=tmp_dir)
            assert (
                expected_tmpl.format(suffix=suffix)
                == dir2dict(tmp_dir)["/etc/network/interfaces"]
            )


class TestNetplanNetRendering:
    @pytest.mark.parametrize(
        "network_cfg,expected",
        [
            pytest.param(
                None,
                """
                network:
                  ethernets:
                    eth1000:
                      dhcp4: true
                      dhcp6: true
                      match:
                        macaddress: 07-1c-c6-75-a4-be
                      set-name: eth1000
                  version: 2
                """,
                id="default_generation",
            ),
            # Asserts a netconf v1 with a physical device and two gateways
            # does not produce deprecated keys, `gateway{46}`, in Netplan v2
            pytest.param(
                """
                version: 1
                config:
                  - type: physical
                    name: interface0
                    mac_address: '00:11:22:33:44:55'
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                      - type: static
                        address: 11.0.0.11/24
                        gateway: 11.0.0.1
                """,
                """
                network:
                  version: 2
                  ethernets:
                    interface0:
                      addresses:
                      - 192.168.23.14/27
                      - 11.0.0.11/24
                      match:
                        macaddress: 00:11:22:33:44:55
                      set-name: interface0
                      routes:
                        - to: default
                          via: 192.168.23.1
                        - to: default
                          via: 11.0.0.1
                """,
                id="physical_gateway46",
            ),
            # Asserts a netconf v1 with a bond device and two gateways
            # does not produce deprecated keys, `gateway{46}`, in Netplan v2
            pytest.param(
                """
                version: 1
                config:
                  - type: bond
                    name: bond0
                    bond_interfaces:
                    - eth0
                    - eth1
                    params: {}
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                      - type: static
                        address: 11.0.0.11/24
                        gateway: 11.0.0.1
                """,
                """
                network:
                  version: 2
                  bonds:
                    bond0:
                      addresses:
                      - 192.168.23.14/27
                      - 11.0.0.11/24
                      interfaces:
                      - eth0
                      - eth1
                      routes:
                        - to: default
                          via: 192.168.23.1
                        - to: default
                          via: 11.0.0.1
                    eth0: {}
                    eth1: {}
                """,
                id="bond_gateway46",
            ),
            # Asserts a netconf v1 with a bridge device and two gateways
            # does not produce deprecated keys, `gateway{46}`, in Netplan v2
            pytest.param(
                """
                version: 1
                config:
                  - type: bridge
                    name: bridge0
                    bridge_interfaces:
                    - eth0
                    params: {}
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                      - type: static
                        address: 11.0.0.11/24
                        gateway: 11.0.0.1
                """,
                """
                network:
                  version: 2
                  bridges:
                    bridge0:
                      addresses:
                      - 192.168.23.14/27
                      - 11.0.0.11/24
                      interfaces:
                      - eth0
                      routes:
                        - to: default
                          via: 192.168.23.1
                        - to: default
                          via: 11.0.0.1
                """,
                id="bridge_gateway46",
            ),
            # Asserts a netconf v1 with a vlan device and two gateways
            # does not produce deprecated keys, `gateway{46}`, in Netplan v2
            pytest.param(
                """
                version: 1
                config:
                  - type: vlan
                    name: vlan0
                    vlan_link: eth0
                    vlan_id: 101
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                      - type: static
                        address: 11.0.0.11/24
                        gateway: 11.0.0.1
                """,
                """
                network:
                  version: 2
                  vlans:
                    vlan0:
                      addresses:
                      - 192.168.23.14/27
                      - 11.0.0.11/24
                      id: 101
                      link: eth0
                      routes:
                        - to: default
                          via: 192.168.23.1
                        - to: default
                          via: 11.0.0.1
                """,
                id="vlan_gateway46",
            ),
            # Asserts a netconf v1 with a nameserver device and two gateways
            # does not produce deprecated keys, `gateway{46}`, in Netplan v2
            pytest.param(
                """
                version: 1
                config:
                  - type: physical
                    name: interface0
                    mac_address: '00:11:22:33:44:55'
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                  - type: nameserver
                    address:
                      - 192.168.23.14/27
                      - 11.0.0.11/24
                    search:
                    - exemplary
                    subnets:
                      - type: static
                        address: 192.168.23.14/27
                        gateway: 192.168.23.1
                      - type: static
                        address: 11.0.0.11/24
                        gateway: 11.0.0.1
                """,
                """
                network:
                  version: 2
                  ethernets:
                    interface0:
                      addresses:
                      - 192.168.23.14/27
                      match:
                        macaddress: 00:11:22:33:44:55
                      nameservers:
                        addresses:
                        - 192.168.23.14/27
                        - 11.0.0.11/24
                        search:
                        - exemplary
                      set-name: interface0
                      routes:
                        - to: default
                          via: 192.168.23.1
                """,
                id="nameserver_gateway4",
            ),
            # Asserts a netconf v1 with two subnets with two gateways does
            # not clash
            pytest.param(
                """
                version: 1
                config:
                  - type: physical
                    name: interface0
                    mac_address: '00:11:22:33:44:55'
                    subnets:
                      - type: static
                        address: 192.168.23.14/24
                        gateway: 192.168.23.1
                      - type: static
                        address: 10.184.225.122
                        routes:
                          - network: 10.176.0.0
                            gateway: 10.184.225.121
                """,
                """
                network:
                  version: 2
                  ethernets:
                    interface0:
                      addresses:
                      - 192.168.23.14/24
                      - 10.184.225.122/24
                      match:
                        macaddress: 00:11:22:33:44:55
                      routes:
                      -   to: default
                          via: 192.168.23.1
                      -   to: 10.176.0.0/24
                          via: 10.184.225.121
                      set-name: interface0
                """,
                id="two_subnets_old_new_gateway46",
            ),
            # Asserts a netconf v1 with one subnet with two gateways does
            # not clash
            pytest.param(
                """
                version: 1
                config:
                  - type: physical
                    name: interface0
                    mac_address: '00:11:22:33:44:55'
                    subnets:
                      - type: static
                        address: 192.168.23.14/24
                        gateway: 192.168.23.1
                        routes:
                          - network: 192.167.225.122
                            gateway: 192.168.23.1
                """,
                """
                network:
                  version: 2
                  ethernets:
                    interface0:
                      addresses:
                      - 192.168.23.14/24
                      match:
                        macaddress: 00:11:22:33:44:55
                      routes:
                      -   to: default
                          via: 192.168.23.1
                      -   to: 192.167.225.122/24
                          via: 192.168.23.1
                      set-name: interface0
                """,
                id="one_subnet_old_new_gateway46",
            ),
            # Assert gateways outside of the subnet's network are added with
            # the on-link flag
            pytest.param(
                """
                version: 1
                config:
                  - type: physical
                    name: interface0
                    mac_address: '00:11:22:33:44:55'
                    subnets:
                      - type: static
                        address: 192.168.23.14/24
                        gateway: 192.168.255.1
                      - type: static
                        address: 2001:cafe::/64
                        gateway: 2001:ffff::1
                """,
                """
                network:
                  version: 2
                  ethernets:
                    interface0:
                      addresses:
                      - 192.168.23.14/24
                      - 2001:cafe::/64
                      match:
                        macaddress: 00:11:22:33:44:55
                      routes:
                      -   to: default
                          via: 192.168.255.1
                          on-link: true
                      -   to: default
                          via: 2001:ffff::1
                          on-link: true
                      set-name: interface0
                """,
                id="onlink_gateways",
            ),
        ],
    )
    @mock.patch(
        "cloudinit.net.netplan.Renderer.features",
        new_callable=mock.PropertyMock(return_value=[]),
    )
    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.netplan._clean_default")
    @mock.patch("cloudinit.net.openvswitch_is_installed", return_value=False)
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_render(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        _openvswitch_is_installed,
        mock_clean_default,
        m_get_cmdline,
        m_renderer_features,
        network_cfg: Optional[str],
        expected: str,
        tmpdir,
    ):
        tmp_dir = str(tmpdir)
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        if network_cfg is None:
            network_cfg = net.generate_fallback_config()
        else:
            network_cfg = yaml.safe_load(network_cfg)
        assert isinstance(network_cfg, dict)

        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = "netplan.yaml"
        renderer = netplan.Renderer(
            {"netplan_path": render_target, "postcmds": False}
        )
        renderer.render_network_state(ns, target=render_dir)

        assert os.path.exists(os.path.join(render_dir, render_target))
        with open(os.path.join(render_dir, render_target)) as fh:
            contents = fh.read()
            print(contents)

        assert yaml.safe_load(expected) == yaml.safe_load(contents)
        assert 1, mock_clean_default.call_count


class TestNetplanCleanDefault:
    snapd_known_path = "etc/netplan/00-snapd-config.yaml"
    snapd_known_content = textwrap.dedent(
        """\
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
        """
    )
    stub_known = {
        "run/systemd/network/10-netplan-all-en.network": "foo-en",
        "run/systemd/network/10-netplan-all-eth.network": "foo-eth",
        "run/systemd/generator/netplan.stamp": "stamp",
    }

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def test_clean_known_config_cleaned(self):
        content = {
            self.snapd_known_path: self.snapd_known_content,
        }
        content.update(self.stub_known)
        tmpd = self.tmp_dir()
        files = sorted(populate_dir(tmpd, content))
        netplan._clean_default(target=tmpd)
        found = [t for t in files if os.path.exists(t)]
        assert [] == found

    def test_clean_unknown_config_not_cleaned(self):
        content = {
            self.snapd_known_path: self.snapd_known_content,
        }
        content.update(self.stub_known)
        content[self.snapd_known_path] += "# user put a comment\n"
        tmpd = self.tmp_dir()
        files = sorted(populate_dir(tmpd, content))
        netplan._clean_default(target=tmpd)
        found = [t for t in files if os.path.exists(t)]
        assert files == found

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
        expected = [subp.target_path(tmpd, f) for f in (astamp, anet, ayaml)]
        assert sorted(expected) == found


class TestNetplanPostcommands:
    mycfg = {
        "config": [
            {
                "type": "physical",
                "name": "eth0",
                "mac_address": "c0:d6:9f:2c:e8:80",
                "subnets": [{"type": "dhcp"}],
            }
        ],
        "version": 1,
    }

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    @mock.patch.object(netplan.Renderer, "_netplan_generate")
    @mock.patch.object(netplan.Renderer, "_net_setup_link")
    @mock.patch("cloudinit.subp.subp")
    def test_netplan_render_calls_postcmds(
        self, mock_subp, mock_net_setup_link, mock_netplan_generate
    ):
        tmp_dir = self.tmp_dir()
        ns = network_state.parse_net_config_data(self.mycfg, skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = "netplan.yaml"
        renderer = netplan.Renderer(
            {"netplan_path": render_target, "postcmds": True}
        )
        mock_subp.side_effect = iter([subp.ProcessExecutionError])
        renderer.render_network_state(ns, target=render_dir)

        mock_netplan_generate.assert_called_with(run=True, config_changed=True)
        mock_net_setup_link.assert_called_with(run=True)

    @mock.patch("cloudinit.util.get_cmdline")
    @mock.patch("cloudinit.util.SeLinuxGuard")
    @mock.patch.object(netplan, "get_devicelist")
    @mock.patch("cloudinit.subp.subp")
    def test_netplan_postcmds(
        self, mock_subp, mock_devlist, mock_sel, m_get_cmdline
    ):
        mock_sel.__enter__ = mock.Mock(return_value=False)
        mock_sel.__exit__ = mock.Mock()
        mock_devlist.side_effect = [["lo"]]
        tmp_dir = self.tmp_dir()
        ns = network_state.parse_net_config_data(self.mycfg, skip_broken=False)

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = "netplan.yaml"
        renderer = netplan.Renderer(
            {"netplan_path": render_target, "postcmds": True}
        )
        mock_subp.side_effect = iter(
            [
                ("", ""),
                ("", ""),
            ]
        )
        expected = [
            mock.call(["netplan", "generate"], capture=True),
            mock.call(
                [
                    "udevadm",
                    "test-builtin",
                    "net_setup_link",
                    "/sys/class/net/lo",
                ],
                capture=True,
            ),
        ]
        with mock.patch.object(os.path, "islink", return_value=True):
            renderer.render_network_state(ns, target=render_dir)
            mock_subp.assert_has_calls(expected)


class TestEniNetworkStateToEni:
    mycfg = {
        "config": [
            {
                "type": "physical",
                "name": "eth0",
                "mac_address": "c0:d6:9f:2c:e8:80",
                "subnets": [{"type": "dhcp"}],
            }
        ],
        "version": 1,
    }
    my_mac = "c0:d6:9f:2c:e8:80"

    def test_no_header(self):
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            render_hwaddress=True,
        )
        assert self.my_mac in rendered
        assert "hwaddress" in rendered

    def test_with_header(self):
        header = "# hello world\n"
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            header=header,
            render_hwaddress=True,
        )
        assert header in rendered
        assert self.my_mac in rendered

    def test_no_hwaddress(self):
        rendered = eni.network_state_to_eni(
            network_state=network_state.parse_net_config_data(self.mycfg),
            render_hwaddress=False,
        )
        assert self.my_mac not in rendered
        assert "hwaddress" not in rendered


class TestCmdlineConfigParsing:
    simple_cfg = {
        "config": [
            {
                "type": "physical",
                "name": "eth0",
                "mac_address": "c0:d6:9f:2c:e8:80",
                "subnets": [{"type": "dhcp"}],
            }
        ]
    }

    def test_cmdline_convert_dhcp(self):
        found = cmdline._klibc_to_config_entry(DHCP_CONTENT_1)
        assert found == ("eth0", DHCP_EXPECTED_1)

    def test_cmdline_convert_dhcp6(self):
        found = cmdline._klibc_to_config_entry(DHCP6_CONTENT_1)
        assert found == ("eno1", DHCP6_EXPECTED_1)

    def test_cmdline_convert_static(self):
        found1 = cmdline._klibc_to_config_entry(STATIC_CONTENT_1)
        assert found1 == ("eth1", STATIC_EXPECTED_1)
        found2 = cmdline._klibc_to_config_entry(STATIC_CONTENT_2)
        assert found2 == ("eth1", STATIC_EXPECTED_1)
        found3 = cmdline._klibc_to_config_entry(STATIC_CONTENT_3)
        assert found3 == ("eth1", STATIC_EXPECTED_1)

    def test_config_from_cmdline_net_cfg(self):
        files = []
        pairs = (
            ("net-eth0.cfg", DHCP_CONTENT_1),
            ("net-eth1.cfg", STATIC_CONTENT_1),
        )

        macs = {"eth1": "b8:ae:ed:75:ff:2b", "eth0": "b8:ae:ed:75:ff:2a"}

        dhcp = copy.deepcopy(DHCP_EXPECTED_1)
        dhcp["mac_address"] = macs["eth0"]

        static = copy.deepcopy(STATIC_EXPECTED_1)
        static["mac_address"] = macs["eth1"]

        expected = {"version": 1, "config": [dhcp, static]}
        with temp_utils.tempdir() as tmpd:
            for fname, content in pairs:
                fp = os.path.join(tmpd, fname)
                files.append(fp)
                util.write_file(fp, content)

            found = cmdline.config_from_klibc_net_cfg(
                files=files, mac_addrs=macs
            )
            assert found == expected

    def test_cmdline_with_b64(self):
        data = base64.b64encode(json.dumps(self.simple_cfg).encode())
        encoded_text = data.decode()
        raw_cmdline = "ro network-config=" + encoded_text + " root=foo"
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        assert found == self.simple_cfg

    def test_cmdline_with_net_config_disabled(self):
        raw_cmdline = "ro network-config=disabled root=foo"
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        assert found == {"config": "disabled"}

    def test_cmdline_with_net_config_unencoded_logs_error(self, caplog):
        """network-config cannot be unencoded besides 'disabled'."""
        raw_cmdline = "ro network-config={config:disabled} root=foo"
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        assert found is None
        expected_log = (
            "Expected base64 encoded kernel command line parameter"
            " network-config. Ignoring network-config={config:disabled}."
        )
        assert expected_log in caplog.text

    def test_cmdline_with_b64_gz(self):
        data = _gzip_data(json.dumps(self.simple_cfg).encode())
        encoded_text = base64.b64encode(data).decode()
        raw_cmdline = "ro network-config=" + encoded_text + " root=foo"
        found = cmdline.read_kernel_cmdline_config(cmdline=raw_cmdline)
        assert found == self.simple_cfg


class TestCmdlineKlibcNetworkConfigSource:
    macs = {
        "eth0": "14:02:ec:42:48:00",
        "eno1": "14:02:ec:42:48:01",
    }

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def test_without_ip(self, fake_filesystem):
        content = {
            "/run/net-eth0.conf": DHCP_CONTENT_1,
            cmdline._OPEN_ISCSI_INTERFACE_FILE: "eth0\n",
        }
        exp1 = copy.deepcopy(DHCP_EXPECTED_1)
        exp1["mac_address"] = self.macs["eth0"]

        populate_dir(fake_filesystem, content)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline="foo root=/root/bar",
            _mac_addrs=self.macs,
        )
        assert src.is_applicable()
        found = src.render_config()
        assert found["version"] == 1
        assert found["config"] == [exp1]

    def test_with_ip(self, fake_filesystem):
        content = {"/run/net-eth0.conf": DHCP_CONTENT_1}
        exp1 = copy.deepcopy(DHCP_EXPECTED_1)
        exp1["mac_address"] = self.macs["eth0"]

        populate_dir(fake_filesystem, content)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline="foo ip=dhcp",
            _mac_addrs=self.macs,
        )
        assert src.is_applicable()
        found = src.render_config()
        assert found["version"] == 1
        assert found["config"] == [exp1]

    def test_with_ip6(self, fake_filesystem):
        content = {"/run/net6-eno1.conf": DHCP6_CONTENT_1}
        populate_dir(fake_filesystem, content)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline="foo ip6=dhcp root=/dev/sda",
            _mac_addrs=self.macs,
        )
        assert src.is_applicable()
        found = src.render_config()
        assert found == {
            "version": 1,
            "config": [
                {
                    "type": "physical",
                    "name": "eno1",
                    "mac_address": self.macs["eno1"],
                    "subnets": [
                        {
                            "dns_nameservers": ["2001:67c:1562:8010::2:1"],
                            "control": "manual",
                            "type": "dhcp6",
                            "netmask": "64",
                        }
                    ],
                }
            ],
        }

    def test_with_no_ip_or_ip6(self):
        # if there is no ip= or ip6= on cmdline, return value should be None
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline="foo root=/dev/sda",
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_with_faux_ip(self):
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline="foo iscsi_target_ip=root=/dev/sda",
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_empty_cmdline(self):
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline="",
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_whitespace_cmdline(self):
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline="          ",
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_cmdline_no_lhand(self):
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline="=wut",
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_cmdline_embedded_ip(self):
        content = {"net6-eno1.conf": DHCP6_CONTENT_1}
        files = sorted(populate_dir(self.tmp_dir(), content))
        src = cmdline.KlibcNetworkConfigSource(
            _files=files,
            _cmdline='opt="some things and ip=foo"',
            _mac_addrs=self.macs,
        )
        assert not src.is_applicable()

    def test_with_both_ip_ip6(self, fake_filesystem):
        content = {
            "/run/net-eth0.conf": DHCP_CONTENT_1,
            "/run/net6-eth0.conf": DHCP6_CONTENT_1.replace("eno1", "eth0"),
        }
        eth0 = copy.deepcopy(DHCP_EXPECTED_1)
        eth0["mac_address"] = self.macs["eth0"]
        eth0["subnets"].append(
            {
                "control": "manual",
                "type": "dhcp6",
                "netmask": "64",
                "dns_nameservers": ["2001:67c:1562:8010::2:1"],
            }
        )
        expected = [eth0]

        populate_dir(fake_filesystem, content)

        src = cmdline.KlibcNetworkConfigSource(
            _cmdline="foo ip=dhcp ip6=dhcp",
            _mac_addrs=self.macs,
        )

        assert src.is_applicable()
        found = src.render_config()
        assert found["version"] == 1
        assert found["config"] == expected


class TestReadInitramfsConfig:
    def _config_source_cls_mock(self, is_applicable, render_config=None):
        return lambda: mock.Mock(
            is_applicable=lambda: is_applicable,
            render_config=lambda: render_config,
        )

    def test_no_sources(self):
        with mock.patch("cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES", []):
            assert cmdline.read_initramfs_config() is None

    def test_no_applicable_sources(self):
        sources = [
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
        ]
        with mock.patch(
            "cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES", sources
        ):
            assert cmdline.read_initramfs_config() is None

    def test_one_applicable_source(self):
        expected_config = object()
        sources = [
            self._config_source_cls_mock(
                is_applicable=True,
                render_config=expected_config,
            ),
        ]
        with mock.patch(
            "cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES", sources
        ):
            assert expected_config == cmdline.read_initramfs_config()

    def test_one_applicable_source_after_inapplicable_sources(self):
        expected_config = object()
        sources = [
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(is_applicable=False),
            self._config_source_cls_mock(
                is_applicable=True,
                render_config=expected_config,
            ),
        ]
        with mock.patch(
            "cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES", sources
        ):
            assert expected_config == cmdline.read_initramfs_config()

    def test_first_applicable_source_is_used(self):
        first_config, second_config = object(), object()
        sources = [
            self._config_source_cls_mock(
                is_applicable=True,
                render_config=first_config,
            ),
            self._config_source_cls_mock(
                is_applicable=True,
                render_config=second_config,
            ),
        ]
        with mock.patch(
            "cloudinit.net.cmdline._INITRAMFS_CONFIG_SOURCES", sources
        ):
            assert first_config == cmdline.read_initramfs_config()


class TestNetplanRoundTrip:
    NETPLAN_INFO_OUT = textwrap.dedent(
        """
    netplan.io:
      features:
        - dhcp-use-domains
        - ipv6-mtu
      website: https://netplan.io/
    """
    )

    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory, mocker):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))
        mocker.patch(
            "cloudinit.net.netplan.subp.subp",
            return_value=(self.NETPLAN_INFO_OUT, ""),
        )

    def _render_and_read(
        self, network_config=None, state=None, netplan_path=None, target=None
    ):
        if target is None:
            target = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if netplan_path is None:
            netplan_path = "etc/netplan/50-cloud-init.yaml"

        renderer = netplan.Renderer(config={"netplan_path": netplan_path})

        renderer.render_network_state(ns, target=target)
        return dir2dict(target)

    @pytest.mark.parametrize(
        "expected_name,yaml_version",
        [
            ("bond_v1", "yaml"),
            ("bond_v2", "yaml"),
            ("small_v1", "yaml"),
            ("v4_and_v6", "yaml_v1"),
            ("v4_and_v6", "yaml_v2"),
            ("v1_ipv4_and_ipv6_static", "yaml_v1"),
            ("v2_ipv4_and_ipv6_static", "yaml_v2"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("dhcpv6_accept_ra", "yaml_v1"),
            ("dhcpv6_reject_ra", "yaml_v1"),
            ("ipv6_slaac", "yaml"),
            ("dhcpv6_stateless", "yaml"),
            ("dhcpv6_stateful", "yaml"),
            ("wakeonlan_disabled", "yaml_v2"),
            ("wakeonlan_enabled", "yaml_v2"),
            ("large_v1", "yaml"),
            ("manual", "yaml"),
            pytest.param(
                "v1-dns",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="netplan should render interface-level nameservers"
                ),
            ),
        ],
    )
    def test_config(self, expected_name, yaml_version):
        entry = NETWORK_CONFIGS[expected_name]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_version])
        )
        assert yaml.safe_load(entry["expected_netplan"]) == yaml.safe_load(
            files["/etc/netplan/50-cloud-init.yaml"]
        )

    def test_render_output_has_yaml_no_aliases(self):
        entry = {
            "yaml": V1_NAMESERVER_ALIAS,
            "expected_netplan": NETPLAN_NO_ALIAS,
        }
        network_config = yaml.safe_load(entry["yaml"])
        ns = network_state.parse_net_config_data(network_config)
        files = self._render_and_read(state=ns)
        # check for alias
        content = files["/etc/netplan/50-cloud-init.yaml"]

        # test load the yaml to ensure we don't render something not loadable
        # this allows single aliases, but not duplicate ones
        parsed = yaml.safe_load(files["/etc/netplan/50-cloud-init.yaml"])
        assert parsed is not None

        # now look for any alias, avoid rendering them entirely
        # generate the first anchor string using the template
        # as of this writing, looks like "&id001"
        anchor = r"&" + Serializer.ANCHOR_TEMPLATE % 1
        found_alias = re.search(anchor, content, re.MULTILINE)
        if found_alias:
            msg = "Error at: %s\nContent:\n%s" % (found_alias, content)
            raise ValueError("Found yaml alias in rendered netplan: " + msg)

        assert (
            entry["expected_netplan"].splitlines()
            == files["/etc/netplan/50-cloud-init.yaml"].splitlines()
        )

    def test_render_output_supports_both_grat_arp_spelling(self):
        entry = {
            "yaml": NETPLAN_BOND_GRAT_ARP,
            "expected_netplan": NETPLAN_BOND_GRAT_ARP.replace(
                "gratuitious", "gratuitous"
            ),
        }
        network_config = yaml.safe_load(entry["yaml"]).get("network")
        files = self._render_and_read(network_config=network_config)
        assert (
            entry["expected_netplan"].splitlines()
            == files["/etc/netplan/50-cloud-init.yaml"].splitlines()
        )


class TestEniRoundTrip:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def _render_and_read(
        self,
        network_config=None,
        state=None,
        eni_path=None,
        netrules_path=None,
        dir=None,
    ):
        if dir is None:
            dir = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if eni_path is None:
            eni_path = "etc/network/interfaces"

        renderer = eni.Renderer(
            config={"eni_path": eni_path, "netrules_path": netrules_path}
        )

        renderer.render_network_state(ns, target=dir)
        return dir2dict(dir)

    def testsimple_convert_and_render(self):
        network_config = eni.convert_eni_data(EXAMPLE_ENI)
        files = self._render_and_read(network_config=network_config)
        assert (
            RENDERED_ENI.splitlines()
            == files["/etc/network/interfaces"].splitlines()
        )

    @pytest.mark.parametrize(
        "expected_name,yaml_version",
        [
            ("large_v1", "yaml"),
            pytest.param(
                "large_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason=(
                        "MAC for bond and bridge not being rendered. "
                        "bond-miimon is used rather than bond_miimon. "
                        "No rendering of bridge_gcint. "
                        "No rendering of bridge_waitport. "
                        "IPv6 routes added to IPv4 section. "
                        "DNS rendering inconsistencies."
                    )
                ),
            ),
            ("small_v1", "yaml"),
            pytest.param(
                "small_v2", "yaml", marks=pytest.mark.xfail(reason="GH-4219")
            ),
            ("v4_and_v6", "yaml_v1"),
            ("v4_and_v6", "yaml_v2"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("v1_ipv4_and_ipv6_static", "yaml_v1"),
            ("v2_ipv4_and_ipv6_static", "yaml_v2"),
            ("dhcpv6_stateless", "yaml"),
            ("ipv6_slaac", "yaml"),
            pytest.param(
                "dhcpv6_stateful",
                "yaml",
                marks=pytest.mark.xfail(
                    reason="Test never passed due to typo in name"
                ),
            ),
            ("dhcpv6_accept_ra", "yaml_v1"),
            ("dhcpv6_accept_ra", "yaml_v2"),
            ("dhcpv6_reject_ra", "yaml_v1"),
            ("dhcpv6_reject_ra", "yaml_v2"),
            ("wakeonlan_disabled", "yaml_v2"),
            ("wakeonlan_enabled", "yaml_v2"),
            ("manual", "yaml"),
            ("bond_v1", "yaml"),
            pytest.param(
                "bond_v2",
                "yaml",
                marks=pytest.mark.xfail(
                    reason=(
                        "Rendering bond_miimon rather than bond-miimon. "
                        "Using pre-down/post-up routes for gateway rather "
                        "gateway. "
                        "Adding ipv6 routes to ipv4 section"
                    )
                ),
            ),
            pytest.param(
                "v1-dns", "yaml", marks=pytest.mark.xfail(reason="GH-4219")
            ),
            pytest.param(
                "v2-dns", "yaml", marks=pytest.mark.xfail(reason="GH-4219")
            ),
        ],
    )
    def test_config(self, expected_name, yaml_version):
        entry = NETWORK_CONFIGS[expected_name]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_version])
        )
        assert (
            entry["expected_eni"].splitlines()
            == files["/etc/network/interfaces"].splitlines()
        )

    def test_routes_rendered(self):
        # as reported in bug 1649652
        conf = [
            {
                "name": "eth0",
                "type": "physical",
                "subnets": [
                    {
                        "address": "172.23.31.42/26",
                        "dns_nameservers": [],
                        "gateway": "172.23.31.2",
                        "type": "static",
                    }
                ],
            },
            {
                "type": "route",
                "id": 4,
                "metric": 0,
                "destination": "10.0.0.0/12",
                "gateway": "172.23.31.1",
            },
            {
                "type": "route",
                "id": 5,
                "metric": 0,
                "destination": "192.168.2.0/16",
                "gateway": "172.23.31.1",
            },
            {
                "type": "route",
                "id": 6,
                "metric": 1,
                "destination": "10.0.200.0/16",
                "gateway": "172.23.31.1",
            },
            {
                "type": "route",
                "id": 7,
                "metric": 1,
                "destination": "10.0.0.100/32",
                "gateway": "172.23.31.1",
            },
        ]

        files = self._render_and_read(
            network_config={"config": conf, "version": 1}
        )
        expected = [
            "auto lo",
            "iface lo inet loopback",
            "auto eth0",
            "iface eth0 inet static",
            "    address 172.23.31.42/26",
            "    gateway 172.23.31.2",
            "post-up route add -net 10.0.0.0/12 gw "
            "172.23.31.1 metric 0 || true",
            "pre-down route del -net 10.0.0.0/12 gw "
            "172.23.31.1 metric 0 || true",
            "post-up route add -net 192.168.2.0/16 gw "
            "172.23.31.1 metric 0 || true",
            "pre-down route del -net 192.168.2.0/16 gw "
            "172.23.31.1 metric 0 || true",
            "post-up route add -net 10.0.200.0/16 gw "
            "172.23.31.1 metric 1 || true",
            "pre-down route del -net 10.0.200.0/16 gw "
            "172.23.31.1 metric 1 || true",
            "post-up route add -host 10.0.0.100/32 gw "
            "172.23.31.1 metric 1 || true",
            "pre-down route del -host 10.0.0.100/32 gw "
            "172.23.31.1 metric 1 || true",
        ]
        found = files["/etc/network/interfaces"].splitlines()

        assert expected == [line for line in found if line]

    def test_ipv6_static_routes(self):
        # as reported in bug 1818669
        conf = [
            {
                "name": "eno3",
                "type": "physical",
                "subnets": [
                    {
                        "address": "fd00::12/64",
                        "dns_nameservers": ["fd00:2::15"],
                        "gateway": "fd00::1",
                        "ipv6": True,
                        "type": "static",
                        "routes": [
                            {
                                "netmask": "32",
                                "network": "fd00:12::",
                                "gateway": "fd00::2",
                            },
                            {"network": "fd00:14::", "gateway": "fd00::3"},
                            {
                                "destination": "fe00:14::/48",
                                "gateway": "fe00::4",
                                "metric": 500,
                            },
                            {
                                "gateway": "192.168.23.1",
                                "metric": 999,
                                "netmask": 24,
                                "network": "192.168.23.0",
                            },
                            {
                                "destination": "10.23.23.0/24",
                                "gateway": "10.23.23.2",
                                "metric": 300,
                            },
                        ],
                    }
                ],
            },
        ]

        files = self._render_and_read(
            network_config={"config": conf, "version": 1}
        )
        expected = [
            "auto lo",
            "iface lo inet loopback",
            "auto eno3",
            "iface eno3 inet6 static",
            "    address fd00::12/64",
            "    dns-nameservers fd00:2::15",
            "    gateway fd00::1",
            "    post-up route add -A inet6 fd00:12::/32 gw fd00::2 || true",
            "    pre-down route del -A inet6 fd00:12::/32 gw fd00::2 || true",
            "    post-up route add -A inet6 fd00:14::/64 gw fd00::3 || true",
            "    pre-down route del -A inet6 fd00:14::/64 gw fd00::3 || true",
            "    post-up route add -A inet6 fe00:14::/48 gw "
            "fe00::4 metric 500 || true",
            "    pre-down route del -A inet6 fe00:14::/48 gw "
            "fe00::4 metric 500 || true",
            "    post-up route add -net 192.168.23.0/24 gw "
            "192.168.23.1 metric 999 || true",
            "    pre-down route del -net 192.168.23.0/24 gw "
            "192.168.23.1 metric 999 || true",
            "    post-up route add -net 10.23.23.0/24 gw "
            "10.23.23.2 metric 300 || true",
            "    pre-down route del -net 10.23.23.0/24 gw "
            "10.23.23.2 metric 300 || true",
        ]
        found = files["/etc/network/interfaces"].splitlines()

        assert expected == [line for line in found if line]


class TestNetworkdNetRendering:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def create_conf_dict(self, contents):
        content_dict = {}
        for line in contents:
            if line:
                line = line.strip()
                if line and re.search(r"^\[(.+)\]$", line):
                    content_dict[line] = []
                    key = line
                elif line:
                    content_dict[key].append(line)

        return content_dict

    def compare_dicts(self, actual, expected):
        for k, v in actual.items():
            assert sorted(expected[k]) == sorted(v)

    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    @mock.patch("cloudinit.net.util.get_cmdline", return_value="root=myroot")
    @mock.patch("cloudinit.net.sys_dev_path")
    @mock.patch("cloudinit.net.read_sys_net")
    @mock.patch("cloudinit.net.get_devicelist")
    def test_networkd_default_generation(
        self,
        mock_get_devicelist,
        mock_read_sys_net,
        mock_sys_dev_path,
        m_get_cmdline,
        m_chown,
    ):
        tmp_dir = self.tmp_dir()
        _setup_test(
            tmp_dir, mock_get_devicelist, mock_read_sys_net, mock_sys_dev_path
        )

        network_cfg = net.generate_fallback_config()
        ns = network_state.parse_net_config_data(
            network_cfg, skip_broken=False
        )

        render_dir = os.path.join(tmp_dir, "render")
        os.makedirs(render_dir)

        render_target = "etc/systemd/network/10-cloud-init-eth1000.network"
        renderer = networkd.Renderer({})
        renderer.render_network_state(ns, target=render_dir)

        assert os.path.exists(os.path.join(render_dir, render_target))
        with open(os.path.join(render_dir, render_target)) as fh:
            contents = fh.readlines()

        actual = self.create_conf_dict(contents)
        print(actual)

        expected = textwrap.dedent(
            """\
            [Match]
            Name=eth1000
            MACAddress=07-1c-c6-75-a4-be
            [Network]
            DHCP=yes"""
        ).rstrip(" ")

        expected = self.create_conf_dict(expected.splitlines())

        self.compare_dicts(actual, expected)


class TestNetworkdRoundTrip:
    @pytest.fixture(autouse=True)
    def setup(self, tmpdir_factory):
        self.tmp_dir = lambda: str(tmpdir_factory.mktemp("a", numbered=True))

    def create_conf_dict(self, contents):
        content_dict = {}
        for line in contents:
            if line:
                line = line.strip()
                if line and re.search(r"^\[(.+)\]$", line):
                    content_dict[line] = []
                    key = line
                elif line:
                    content_dict[key].append(line)

        return content_dict

    def compare_dicts(self, actual, expected):
        for k, v in actual.items():
            assert sorted(expected[k]) == sorted(v)

    def _render_and_read(
        self, network_config=None, state=None, nwkd_path=None, dir=None
    ):
        if dir is None:
            dir = self.tmp_dir()

        if network_config:
            ns = network_state.parse_net_config_data(network_config)
        elif state:
            ns = state
        else:
            raise ValueError("Expected data or state, got neither")

        if not nwkd_path:
            nwkd_path = "/etc/systemd/network/"

        renderer = networkd.Renderer(config={"network_conf_dir": nwkd_path})

        renderer.render_network_state(ns, target=dir)
        return dir2dict(dir)

    @pytest.mark.parametrize(
        "expected_name,yaml_version",
        [
            ("v4_and_v6", "yaml_v1"),
            ("v4_and_v6", "yaml_v2"),
            ("v1_ipv4_and_ipv6_static", "yaml_v1"),
            ("v2_ipv4_and_ipv6_static", "yaml_v2"),
            ("dhcpv6_only", "yaml_v1"),
            ("dhcpv6_only", "yaml_v2"),
            ("dhcpv6_accept_ra", "yaml_v1"),
            ("dhcpv6_accept_ra", "yaml_v2"),
            ("dhcpv6_reject_ra", "yaml_v1"),
            ("dhcpv6_reject_ra", "yaml_v2"),
        ],
    )
    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    def test_config(self, _m_chown, expected_name, yaml_version):
        nwk_fn = "/etc/systemd/network/10-cloud-init-iface0.network"
        entry = NETWORK_CONFIGS[expected_name]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry[yaml_version])
        )

        actual = files[nwk_fn].splitlines()
        actual = self.create_conf_dict(actual)

        expected = entry["expected_networkd"].splitlines()
        expected = self.create_conf_dict(expected)

        self.compare_dicts(actual, expected)

    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    def testsimple_render_small_networkd_v1(self, m_chown):
        nwk_fn1 = "/etc/systemd/network/10-cloud-init-eth99.network"
        nwk_fn2 = "/etc/systemd/network/10-cloud-init-eth1.network"
        entry = NETWORK_CONFIGS["small_v1"]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )

        actual = files[nwk_fn1].splitlines()
        actual = self.create_conf_dict(actual)

        expected = entry["expected_networkd_eth99"].splitlines()
        expected = self.create_conf_dict(expected)

        self.compare_dicts(actual, expected)

        actual = files[nwk_fn2].splitlines()
        actual = self.create_conf_dict(actual)

        expected = entry["expected_networkd_eth1"].splitlines()
        expected = self.create_conf_dict(expected)

        self.compare_dicts(actual, expected)

    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    def testsimple_render_small_networkd_v2(self, m_chown):
        nwk_fn1 = "/etc/systemd/network/10-cloud-init-eth99.network"
        nwk_fn2 = "/etc/systemd/network/10-cloud-init-eth1.network"
        entry = NETWORK_CONFIGS["small_v2"]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )

        actual = files[nwk_fn1].splitlines()
        actual = self.create_conf_dict(actual)

        expected = entry["expected_networkd_eth99"].splitlines()
        expected = self.create_conf_dict(expected)

        self.compare_dicts(actual, expected)

        actual = files[nwk_fn2].splitlines()
        actual = self.create_conf_dict(actual)

        expected = entry["expected_networkd_eth1"].splitlines()
        expected = self.create_conf_dict(expected)

        self.compare_dicts(actual, expected)

    @pytest.mark.xfail(
        reason="DNS and Domains getting rendered on multiple lines"
    )
    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    def test_v1_dns(self, m_chown):
        nwk_fn = "/etc/systemd/network/10-cloud-init-eth0.network"
        entry = NETWORK_CONFIGS["v1-dns"]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )

        actual = self.create_conf_dict(files[nwk_fn].splitlines())
        expected = self.create_conf_dict(
            entry["expected_networkd"].splitlines()
        )

        self.compare_dicts(actual, expected)

    @mock.patch("cloudinit.net.util.chownbyname", return_value=True)
    def test_v2_dns(self, m_chown):
        nwk_fn = "/etc/systemd/network/10-cloud-init-eth0.network"
        entry = NETWORK_CONFIGS["v2-dns"]
        files = self._render_and_read(
            network_config=yaml.safe_load(entry["yaml"])
        )

        actual = self.create_conf_dict(files[nwk_fn].splitlines())
        expected = self.create_conf_dict(
            entry["expected_networkd"].splitlines()
        )

        self.compare_dicts(actual, expected)


class TestRenderersSelect:
    @pytest.mark.parametrize(
        "renderer_selected,netplan,eni,sys,network_manager,networkd",
        (
            # -netplan -ifupdown -sys -network-manager -networkd raises error
            (
                net.RendererNotFoundError,
                False,
                False,
                False,
                False,
                False,
            ),
            # -netplan +ifupdown -sys -nm -networkd selects eni
            ("eni", False, True, False, False, False),
            # +netplan +ifupdown -sys -nm -networkd selects eni
            ("eni", True, True, False, False, False),
            # +netplan -ifupdown -sys -nm -networkd selects netplan
            ("netplan", True, False, False, False, False),
            # +netplan -ifupdown -sys -nm -networkd selects netplan
            ("netplan", True, False, False, False, False),
            # -netplan -ifupdown +sys -nm -networkd selects sysconfig
            ("sysconfig", False, False, True, False, False),
            # -netplan -ifupdown +sys +nm -networkd selects sysconfig
            ("sysconfig", False, False, True, True, False),
            # -netplan -ifupdown -sys +nm -networkd selects nm
            ("network-manager", False, False, False, True, False),
            # -netplan -ifupdown -sys +nm +networkd selects nm
            ("network-manager", False, False, False, True, True),
            # -netplan -ifupdown -sys -nm +networkd selects networkd
            ("networkd", False, False, False, False, True),
        ),
    )
    @mock.patch("cloudinit.net.renderers.networkd.available")
    @mock.patch("cloudinit.net.renderers.network_manager.available")
    @mock.patch("cloudinit.net.renderers.netplan.available")
    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_valid_renderer_from_defaults_depending_on_availability(
        self,
        m_eni_avail,
        m_sys_avail,
        m_netplan_avail,
        m_network_manager_avail,
        m_networkd_avail,
        renderer_selected,
        netplan,
        eni,
        sys,
        network_manager,
        networkd,
    ):
        """Assert proper renderer per DEFAULT_PRIORITY given availability."""
        m_eni_avail.return_value = eni  # ifupdown pkg presence
        m_sys_avail.return_value = sys  # sysconfig/ifup/down presence
        m_netplan_avail.return_value = netplan  # netplan presence
        m_network_manager_avail.return_value = network_manager  # NM presence
        m_networkd_avail.return_value = networkd  # networkd presence
        if isinstance(renderer_selected, str):
            (renderer_name, _rnd_class) = renderers.select(
                priority=renderers.DEFAULT_PRIORITY
            )
            assert renderer_selected == renderer_name
        else:
            with pytest.raises(renderer_selected):
                renderers.select(priority=renderers.DEFAULT_PRIORITY)


class TestNetRenderers:
    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_eni_and_sysconfig_available(self, m_eni_avail, m_sysc_avail):
        m_eni_avail.return_value = True
        m_sysc_avail.return_value = True
        found = renderers.search(priority=["sysconfig", "eni"], first=False)
        names = [f[0] for f in found]
        assert ["sysconfig", "eni"] == names

    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_search_returns_empty_on_none(self, m_eni_avail):
        m_eni_avail.return_value = False
        found = renderers.search(priority=["eni"], first=False)
        assert [] == found

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_first_in_priority(self, m_eni_avail, m_sysc_avail):
        # available should only be called until one is found.
        m_eni_avail.return_value = True
        m_sysc_avail.side_effect = Exception("Should not call me")
        found = renderers.search(priority=["eni", "sysconfig"], first=True)[0]
        assert ["eni"] == [found[0]]

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_select_positive(self, m_eni_avail, m_sysc_avail):
        m_eni_avail.return_value = True
        m_sysc_avail.return_value = False
        found = renderers.select(priority=["sysconfig", "eni"])
        assert "eni" == found[0]

    @mock.patch("cloudinit.net.renderers.sysconfig.available")
    @mock.patch("cloudinit.net.renderers.eni.available")
    def test_select_none_found_raises(self, m_eni_avail, m_sysc_avail):
        # if select finds nothing, should raise exception.
        m_eni_avail.return_value = False
        m_sysc_avail.return_value = False

        pytest.raises(
            net.RendererNotFoundError,
            renderers.select,
            priority=["sysconfig", "eni"],
        )

    @mock.patch("cloudinit.net.sysconfig.available")
    @mock.patch("cloudinit.util.system_info")
    def test_sysconfig_available_uses_variant_mapping(self, m_info, m_avail):
        m_avail.return_value = True
        variants = [
            "suse",
            "centos",
            "eurolinux",
            "fedora",
            "rhel",
        ]
        for distro_name in variants:
            m_info.return_value = {"variant": distro_name}
            if hasattr(util.system_info, "cache_clear"):
                util.system_info.cache_clear()
            result = sysconfig.available()
            assert result

    @mock.patch("cloudinit.net.renderers.networkd.available")
    def test_networkd_available(self, m_nwkd_avail):
        m_nwkd_avail.return_value = True
        found = renderers.search(priority=["networkd"], first=False)
        assert "networkd" == found[0][0]


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestGetInterfaces:
    _data = {
        "bonds": ["bond1"],
        "bridges": ["bridge1"],
        "vlans": ["bond1.101"],
        "own_macs": [
            "enp0s1",
            "enp0s2",
            "bridge1-nic",
            "bridge1",
            "bond1.101",
            "lo",
            "eth1",
        ],
        "macs": {
            "enp0s1": "aa:aa:aa:aa:aa:01",
            "enp0s2": "aa:aa:aa:aa:aa:02",
            "bond1": "aa:aa:aa:aa:aa:01",
            "bond1.101": "aa:aa:aa:aa:aa:01",
            "bridge1": "aa:aa:aa:aa:aa:03",
            "bridge1-nic": "aa:aa:aa:aa:aa:03",
            "lo": "00:00:00:00:00:00",
            "greptap0": "00:00:00:00:00:00",
            "eth1": "aa:aa:aa:aa:aa:01",
            "tun0": None,
        },
        "masters": {},
        "drivers": {
            "enp0s1": "virtio_net",
            "enp0s2": "e1000",
            "bond1": None,
            "bond1.101": None,
            "bridge1": None,
            "bridge1-nic": None,
            "lo": None,
            "greptap0": None,
            "eth1": "mlx4_core",
            "tun0": None,
        },
    }
    data: dict = {}

    def _se_get_devicelist(self):
        return list(self.data["devices"])

    def _se_device_driver(self, name):
        return self.data["drivers"][name]

    def _se_device_devid(self, name):
        return "0x%s" % sorted(list(self.data["drivers"].keys())).index(name)

    def _se_get_interface_mac(self, name):
        return self.data["macs"][name]

    def _se_get_master(self, name):
        return self.data["masters"].get(name)

    def _se_is_bridge(self, name):
        return name in self.data["bridges"]

    def _se_is_vlan(self, name):
        return name in self.data["vlans"]

    def _se_interface_has_own_mac(self, name):
        return name in self.data["own_macs"]

    def _se_is_bond(self, name):
        return name in self.data["bonds"]

    def _se_is_netfailover(self, name):
        return False

    @pytest.fixture
    def mocks(self, mocker):
        self.data = copy.deepcopy(self._data)
        self.data["devices"] = set(list(self.data["macs"].keys()))
        mock_list = (
            "get_devicelist",
            "get_interface_mac",
            "get_master",
            "is_bridge",
            "interface_has_own_mac",
            "is_vlan",
            "device_driver",
            "device_devid",
            "is_bond",
            "is_netfailover",
        )
        all_mocks = {}
        for name in mock_list:
            all_mocks[name] = mocker.patch(
                "cloudinit.net." + name,
                side_effect=getattr(self, "_se_" + name),
            )
        yield all_mocks

    def test_gi_includes_duplicate_macs(self, mocks):
        ret = net.get_interfaces()

        assert "enp0s1" in self._se_get_devicelist()
        assert "eth1" in self._se_get_devicelist()
        found = [ent for ent in ret if "aa:aa:aa:aa:aa:01" in ent]
        assert len(found) == 2

    def test_gi_excludes_any_without_mac_address(self, mocks):
        ret = net.get_interfaces()

        assert "tun0" in self._se_get_devicelist()
        found = [ent for ent in ret if "tun0" in ent]
        assert len(found) == 0

    def test_gi_excludes_stolen_macs(self, mocks):
        ret = net.get_interfaces()
        mocks["interface_has_own_mac"].assert_has_calls(
            [mock.call("enp0s1"), mock.call("bond1")], any_order=True
        )
        expected = [
            ("enp0s2", "aa:aa:aa:aa:aa:02", "e1000", "0x5"),
            ("enp0s1", "aa:aa:aa:aa:aa:01", "virtio_net", "0x4"),
            ("eth1", "aa:aa:aa:aa:aa:01", "mlx4_core", "0x6"),
            ("lo", "00:00:00:00:00:00", None, "0x8"),
            ("bridge1-nic", "aa:aa:aa:aa:aa:03", None, "0x3"),
        ]
        assert sorted(expected) == sorted(ret)

    def test_gi_excludes_bridges(self, mocks):
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a bridge.
        # then expect b1 is the only thing left.
        self.data["macs"]["b1"] = "aa:aa:aa:aa:aa:b1"
        self.data["drivers"]["b1"] = None
        self.data["devices"].add("b1")
        self.data["bonds"] = []
        self.data["own_macs"] = self.data["devices"]
        self.data["bridges"] = [f for f in self.data["devices"] if f != "b1"]
        ret = net.get_interfaces()
        assert [("b1", "aa:aa:aa:aa:aa:b1", None, "0x0")] == ret
        mocks["is_bridge"].assert_has_calls(
            [
                mock.call("bridge1"),
                mock.call("enp0s1"),
                mock.call("bond1"),
                mock.call("b1"),
            ],
            any_order=True,
        )


class TestInterfaceHasOwnMac:
    """Test interface_has_own_mac.  This is admittedly a bit whitebox."""

    @mock.patch("cloudinit.net.read_sys_net_int", return_value=None)
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
        assert interface_has_own_mac("eth0")

    @mock.patch("cloudinit.net.read_sys_net_int", return_value=None)
    def test_strict_with_no_addr_assign_type_raises(self, m_read_sys_net_int):
        with pytest.raises(ValueError):
            interface_has_own_mac("eth0", True)

    @mock.patch("cloudinit.net.read_sys_net_int")
    def test_expected_values(self, m_read_sys_net_int):
        msg = "address_assign_type=%d said to not have own mac"
        for address_assign_type in (0, 1, 3):
            m_read_sys_net_int.return_value = address_assign_type
            assert interface_has_own_mac("eth0", msg % address_assign_type)

        m_read_sys_net_int.return_value = 2
        assert not interface_has_own_mac("eth0")


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestGetInterfacesByMac:
    _data = {
        "bonds": ["bond1"],
        "bridges": ["bridge1"],
        "vlans": ["bond1.101"],
        "own_macs": [
            "enp0s1",
            "enp0s2",
            "bridge1-nic",
            "bridge1",
            "bond1.101",
            "lo",
            "netvsc0-vf",
            "netvsc0",
            "netvsc1",
            "netvsc1-vf",
        ],
        "macs": {
            "enp0s1": "aa:aa:aa:aa:aa:01",
            "enp0s2": "aa:aa:aa:aa:aa:02",
            "bond1": "aa:aa:aa:aa:aa:01",
            "bond1.101": "aa:aa:aa:aa:aa:01",
            "bridge1": "aa:aa:aa:aa:aa:03",
            "bridge1-nic": "aa:aa:aa:aa:aa:03",
            "lo": "00:00:00:00:00:00",
            "greptap0": "00:00:00:00:00:00",
            "netvsc0-vf": "aa:aa:aa:aa:aa:04",
            "netvsc0": "aa:aa:aa:aa:aa:04",
            "netvsc1-vf": "aa:aa:aa:aa:aa:05",
            "netvsc1": "aa:aa:aa:aa:aa:05",
            "tun0": None,
        },
        "drivers": {
            "netvsc0": "hv_netvsc",
            "netvsc0-vf": "foo",
            "netvsc1": "hv_netvsc",
            "netvsc1-vf": "bar",
        },
    }
    data: dict = {}

    @pytest.fixture
    def mocks(self, mocker):
        self.data = copy.deepcopy(self._data)
        self.data["devices"] = set(list(self.data["macs"].keys()))
        mock_list = (
            "get_devicelist",
            "device_driver",
            "get_interface_mac",
            "is_bridge",
            "interface_has_own_mac",
            "is_vlan",
            "get_ib_interface_hwaddr",
        )
        all_mocks = {}
        for name in mock_list:
            all_mocks[name] = mocker.patch(
                "cloudinit.net." + name,
                side_effect=getattr(self, "_se_" + name),
            )
        yield all_mocks

    def _se_get_devicelist(self):
        return list(self.data["devices"])

    def _se_device_driver(self, name):
        return self.data["drivers"].get(name, None)

    def _se_get_interface_mac(self, name):
        return self.data["macs"][name]

    def _se_is_bridge(self, name):
        return name in self.data["bridges"]

    def _se_is_vlan(self, name):
        return name in self.data["vlans"]

    def _se_interface_has_own_mac(self, name):
        return name in self.data["own_macs"]

    def _se_get_ib_interface_hwaddr(self, name, ethernet_format):
        ib_hwaddr = self.data.get("ib_hwaddr", {})
        return ib_hwaddr.get(name, {}).get(ethernet_format)

    def test_raise_exception_on_duplicate_macs(self, mocks):
        self.data["macs"]["bridge1-nic"] = self.data["macs"]["enp0s1"]
        pytest.raises(RuntimeError, net.get_interfaces_by_mac)

    def test_raise_exception_on_duplicate_netvsc_macs(self, mocks):
        self.data["macs"]["netvsc0"] = self.data["macs"]["netvsc1"]
        pytest.raises(RuntimeError, net.get_interfaces_by_mac)

    def test_excludes_any_without_mac_address(self, mocks):
        ret = net.get_interfaces_by_mac()
        assert "tun0" in self._se_get_devicelist()
        assert "tun0" not in ret.values()

    def test_excludes_stolen_macs(self, mocks):
        ret = net.get_interfaces_by_mac()
        mocks["interface_has_own_mac"].assert_has_calls(
            [mock.call("enp0s1"), mock.call("bond1")], any_order=True
        )
        assert {
            "aa:aa:aa:aa:aa:01": "enp0s1",
            "aa:aa:aa:aa:aa:02": "enp0s2",
            "aa:aa:aa:aa:aa:03": "bridge1-nic",
            "00:00:00:00:00:00": "lo",
            "aa:aa:aa:aa:aa:04": "netvsc0",
            "aa:aa:aa:aa:aa:05": "netvsc1",
        } == ret

    def test_excludes_bridges(self, mocks):
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a bridge.
        # then expect b1 is the only thing left.
        self.data["macs"]["b1"] = "aa:aa:aa:aa:aa:b1"
        self.data["devices"].add("b1")
        self.data["bonds"] = []
        self.data["own_macs"] = self.data["devices"]
        self.data["bridges"] = [f for f in self.data["devices"] if f != "b1"]
        ret = net.get_interfaces_by_mac()
        assert {"aa:aa:aa:aa:aa:b1": "b1"} == ret
        mocks["is_bridge"].assert_has_calls(
            [
                mock.call("bridge1"),
                mock.call("enp0s1"),
                mock.call("bond1"),
                mock.call("b1"),
            ],
            any_order=True,
        )

    def test_excludes_vlans(self, mocks):
        # add a device 'b1', make all return they have their "own mac",
        # set everything other than 'b1' to be a vlan.
        # then expect b1 is the only thing left.
        self.data["macs"]["b1"] = "aa:aa:aa:aa:aa:b1"
        self.data["devices"].add("b1")
        self.data["bonds"] = []
        self.data["bridges"] = []
        self.data["own_macs"] = self.data["devices"]
        self.data["vlans"] = [f for f in self.data["devices"] if f != "b1"]
        ret = net.get_interfaces_by_mac()
        assert {"aa:aa:aa:aa:aa:b1": "b1"} == ret
        mocks["is_vlan"].assert_has_calls(
            [
                mock.call("bridge1"),
                mock.call("enp0s1"),
                mock.call("bond1"),
                mock.call("b1"),
            ],
            any_order=True,
        )

    def test_duplicates_of_empty_mac_are_ok(self, mocks):
        """Duplicate macs of 00:00:00:00:00:00 should be skipped."""
        empty_mac = "00:00:00:00:00:00"
        addnics = ("greptap1", "lo", "greptap2")
        self.data["macs"].update(dict((k, empty_mac) for k in addnics))
        self.data["devices"].update(set(addnics))
        self.data["own_macs"].extend(list(addnics))
        ret = net.get_interfaces_by_mac()
        assert "lo" == ret[empty_mac]

    def test_skip_all_zeros(self, mocks):
        """Any mac of 00:... should be skipped."""
        emac1, emac2, emac4, emac6 = (
            "00",
            "00:00",
            "00:00:00:00",
            "00:00:00:00:00:00",
        )
        addnics = {
            "empty1": emac1,
            "emac2a": emac2,
            "emac2b": emac2,
            "emac4": emac4,
            "emac6": emac6,
        }
        self.data["macs"].update(addnics)
        self.data["devices"].update(set(addnics))
        self.data["own_macs"].extend(addnics.keys())
        ret = net.get_interfaces_by_mac()
        assert "lo" == ret["00:00:00:00:00:00"]

    def test_ib(self, mocks):
        ib_addr = "80:00:00:28:fe:80:00:00:00:00:00:00:00:11:22:03:00:33:44:56"
        ib_addr_eth_format = "00:11:22:33:44:56"
        self.data["devices"] = ["enp0s1", "ib0"]
        self.data["own_macs"].append("ib0")
        self.data["macs"]["ib0"] = ib_addr
        self.data["ib_hwaddr"] = {
            "ib0": {True: ib_addr_eth_format, False: ib_addr}
        }
        result = net.get_interfaces_by_mac()
        expected = {
            "aa:aa:aa:aa:aa:01": "enp0s1",
            ib_addr_eth_format: "ib0",
            ib_addr: "ib0",
        }
        assert expected == result


@pytest.mark.parametrize("driver", ("mscc_felix", "fsl_enetc", "qmi_wwan"))
@mock.patch("cloudinit.net.get_sys_class_path")
@mock.patch("cloudinit.util.system_info", return_value={"variant": "ubuntu"})
class TestDuplicateMac:
    def test_duplicate_ignored_macs(
        self, _get_system_info, get_sys_class_path, driver, tmpdir, caplog
    ):
        # Create sysfs representation of network devices and drivers in tmpdir
        sys_net_path = tmpdir.join("class/net")
        get_sys_class_path.return_value = sys_net_path.strpath + "/"
        net_data = {
            "swp0/address": "9a:57:7d:78:47:c0",
            "swp0/addr_assign_type": "0",
            "swp0/device/dev_id": "something",
            "swp1/address": "9a:57:7d:78:47:c0",
            "swp1/addr_assign_type": "0",
            "swp1/device/dev_id": "something else",
        }
        populate_dir(sys_net_path.strpath, net_data)
        # Symlink for device driver
        driver_path = tmpdir.join(f"module/{driver}")
        driver_path.ensure_dir()
        sys_net_path.join("swp0/device/driver").mksymlinkto(driver_path)
        sys_net_path.join("swp1/device/driver").mksymlinkto(driver_path)

        with does_not_raise():
            net.get_interfaces_by_mac()
        pattern = (
            "Ignoring duplicate macs from 'swp[0-1]' and 'swp[0-1]' due to "
            f"driver '{driver}'."
        )
        assert re.search(pattern, caplog.text)


class TestInterfacesSorting:
    def test_natural_order(self):
        data = ["ens5", "ens6", "ens3", "ens20", "ens13", "ens2"]
        assert sorted(data, key=natural_sort_key) == [
            "ens2",
            "ens3",
            "ens5",
            "ens6",
            "ens13",
            "ens20",
        ]
        data2 = ["enp2s0", "enp2s3", "enp0s3", "enp0s13", "enp0s8", "enp1s2"]
        assert sorted(data2, key=natural_sort_key) == [
            "enp0s3",
            "enp0s8",
            "enp0s13",
            "enp1s2",
            "enp2s0",
            "enp2s3",
        ]


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestGetIBHwaddrsByInterface:
    _ib_addr = "80:00:00:28:fe:80:00:00:00:00:00:00:00:11:22:03:00:33:44:56"
    _ib_addr_eth_format = "00:11:22:33:44:56"
    _data = {
        "devices": [
            "enp0s1",
            "enp0s2",
            "bond1",
            "bridge1",
            "bridge1-nic",
            "tun0",
            "ib0",
        ],
        "bonds": ["bond1"],
        "bridges": ["bridge1"],
        "own_macs": ["enp0s1", "enp0s2", "bridge1-nic", "bridge1", "ib0"],
        "macs": {
            "enp0s1": "aa:aa:aa:aa:aa:01",
            "enp0s2": "aa:aa:aa:aa:aa:02",
            "bond1": "aa:aa:aa:aa:aa:01",
            "bridge1": "aa:aa:aa:aa:aa:03",
            "bridge1-nic": "aa:aa:aa:aa:aa:03",
            "tun0": None,
            "ib0": _ib_addr,
        },
        "ib_hwaddr": {"ib0": {True: _ib_addr_eth_format, False: _ib_addr}},
    }
    data: dict = {}

    @pytest.fixture
    def mocks(self, mocker):
        self.data = copy.deepcopy(self._data)
        mock_list = (
            "get_devicelist",
            "get_interface_mac",
            "is_bridge",
            "interface_has_own_mac",
            "get_ib_interface_hwaddr",
        )
        all_mocks = {}
        for name in mock_list:
            all_mocks[name] = mocker.patch(
                "cloudinit.net." + name,
                side_effect=getattr(self, "_se_" + name),
            )
        yield all_mocks

    def _se_get_devicelist(self):
        return self.data["devices"]

    def _se_get_interface_mac(self, name):
        return self.data["macs"][name]

    def _se_is_bridge(self, name):
        return name in self.data["bridges"]

    def _se_interface_has_own_mac(self, name):
        return name in self.data["own_macs"]

    def _se_get_ib_interface_hwaddr(self, name, ethernet_format):
        ib_hwaddr = self.data.get("ib_hwaddr", {})
        return ib_hwaddr.get(name, {}).get(ethernet_format)

    def test_ethernet(self, mocks):
        self.data["devices"].remove("ib0")
        result = net.get_ib_hwaddrs_by_interface()
        expected = {}
        assert expected == result

    def test_ib(self, mocks):
        result = net.get_ib_hwaddrs_by_interface()
        expected = {"ib0": self._ib_addr}
        assert expected == result


def _gzip_data(data):
    with io.BytesIO() as iobuf:
        gzfp = gzip.GzipFile(mode="wb", fileobj=iobuf)
        gzfp.write(data)
        gzfp.close()
        return iobuf.getvalue()


class TestRenameInterfaces:
    @mock.patch("cloudinit.subp.subp")
    def test_rename_all(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "interface0", "virtio_net", "0x3"),
            ("00:11:22:33:44:aa", "interface2", "virtio_net", "0x5"),
        ]
        current_info = {
            "ens3": {
                "downable": True,
                "device_id": "0x3",
                "driver": "virtio_net",
                "mac": "00:11:22:33:44:55",
                "name": "ens3",
                "up": False,
            },
            "ens5": {
                "downable": True,
                "device_id": "0x5",
                "driver": "virtio_net",
                "mac": "00:11:22:33:44:aa",
                "name": "ens5",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "ens3", "name", "interface0"],
                ),
                mock.call(
                    ["ip", "link", "set", "ens5", "name", "interface2"],
                ),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_no_driver_no_device_id(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "interface0", None, None),
            ("00:11:22:33:44:aa", "interface1", None, None),
        ]
        current_info = {
            "eth0": {
                "downable": True,
                "device_id": None,
                "driver": None,
                "mac": "00:11:22:33:44:55",
                "name": "eth0",
                "up": False,
            },
            "eth1": {
                "downable": True,
                "device_id": None,
                "driver": None,
                "mac": "00:11:22:33:44:aa",
                "name": "eth1",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "eth0", "name", "interface0"],
                ),
                mock.call(
                    ["ip", "link", "set", "eth1", "name", "interface1"],
                ),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_all_bounce(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "interface0", "virtio_net", "0x3"),
            ("00:11:22:33:44:aa", "interface2", "virtio_net", "0x5"),
        ]
        current_info = {
            "ens3": {
                "downable": True,
                "device_id": "0x3",
                "driver": "virtio_net",
                "mac": "00:11:22:33:44:55",
                "name": "ens3",
                "up": True,
            },
            "ens5": {
                "downable": True,
                "device_id": "0x5",
                "driver": "virtio_net",
                "mac": "00:11:22:33:44:aa",
                "name": "ens5",
                "up": True,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(["ip", "link", "set", "dev", "ens3", "down"]),
                mock.call(
                    ["ip", "link", "set", "ens3", "name", "interface0"],
                ),
                mock.call(["ip", "link", "set", "dev", "ens5", "down"]),
                mock.call(
                    ["ip", "link", "set", "ens5", "name", "interface2"],
                ),
                mock.call(["ip", "link", "set", "dev", "interface0", "up"]),
                mock.call(["ip", "link", "set", "dev", "interface2", "up"]),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_duplicate_macs(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "eth0", "hv_netvsc", "0x3"),
            ("00:11:22:33:44:55", "vf1", "mlx4_core", "0x5"),
        ]
        current_info = {
            "eth0": {
                "downable": True,
                "device_id": "0x3",
                "driver": "hv_netvsc",
                "mac": "00:11:22:33:44:55",
                "name": "eth0",
                "up": False,
            },
            "eth1": {
                "downable": True,
                "device_id": "0x5",
                "driver": "mlx4_core",
                "mac": "00:11:22:33:44:55",
                "name": "eth1",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(["ip", "link", "set", "eth1", "name", "vf1"]),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_duplicate_macs_driver_no_devid(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "eth0", "hv_netvsc", None),
            ("00:11:22:33:44:55", "vf1", "mlx4_core", None),
        ]
        current_info = {
            "eth0": {
                "downable": True,
                "device_id": "0x3",
                "driver": "hv_netvsc",
                "mac": "00:11:22:33:44:55",
                "name": "eth0",
                "up": False,
            },
            "eth1": {
                "downable": True,
                "device_id": "0x5",
                "driver": "mlx4_core",
                "mac": "00:11:22:33:44:55",
                "name": "eth1",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(["ip", "link", "set", "eth1", "name", "vf1"]),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_multi_mac_dups(self, mock_subp):
        renames = [
            ("00:11:22:33:44:55", "eth0", "hv_netvsc", "0x3"),
            ("00:11:22:33:44:55", "vf1", "mlx4_core", "0x5"),
            ("00:11:22:33:44:55", "vf2", "mlx4_core", "0x7"),
        ]
        current_info = {
            "eth0": {
                "downable": True,
                "device_id": "0x3",
                "driver": "hv_netvsc",
                "mac": "00:11:22:33:44:55",
                "name": "eth0",
                "up": False,
            },
            "eth1": {
                "downable": True,
                "device_id": "0x5",
                "driver": "mlx4_core",
                "mac": "00:11:22:33:44:55",
                "name": "eth1",
                "up": False,
            },
            "eth2": {
                "downable": True,
                "device_id": "0x7",
                "driver": "mlx4_core",
                "mac": "00:11:22:33:44:55",
                "name": "eth2",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)
        mock_subp.assert_has_calls(
            [
                mock.call(["ip", "link", "set", "eth1", "name", "vf1"]),
                mock.call(["ip", "link", "set", "eth2", "name", "vf2"]),
            ]
        )

    @mock.patch("cloudinit.subp.subp")
    def test_rename_macs_case_insensitive(self, mock_subp):
        """_rename_interfaces must support upper or lower case macs."""
        renames = [
            ("aa:aa:aa:aa:aa:aa", "en0", None, None),
            ("BB:BB:BB:BB:BB:BB", "en1", None, None),
            ("cc:cc:cc:cc:cc:cc", "en2", None, None),
            ("DD:DD:DD:DD:DD:DD", "en3", None, None),
        ]
        current_info = {
            "eth0": {
                "downable": True,
                "mac": "AA:AA:AA:AA:AA:AA",
                "name": "eth0",
                "up": False,
            },
            "eth1": {
                "downable": True,
                "mac": "bb:bb:bb:bb:bb:bb",
                "name": "eth1",
                "up": False,
            },
            "eth2": {
                "downable": True,
                "mac": "cc:cc:cc:cc:cc:cc",
                "name": "eth2",
                "up": False,
            },
            "eth3": {
                "downable": True,
                "mac": "DD:DD:DD:DD:DD:DD",
                "name": "eth3",
                "up": False,
            },
        }
        net._rename_interfaces(renames, current_info=current_info)

        expected = [
            mock.call(
                ["ip", "link", "set", "eth%d" % i, "name", "en%d" % i],
            )
            for i in range(len(renames))
        ]
        mock_subp.assert_has_calls(expected)


class TestNetworkState:
    def test_bcast_addr(self):
        """Test mask_and_ipv4_to_bcast_addr proper execution."""
        bcast_addr = mask_and_ipv4_to_bcast_addr
        assert "192.168.1.255" == bcast_addr("255.255.255.0", "192.168.1.1")
        assert "128.42.7.255" == bcast_addr("255.255.248.0", "128.42.5.4")
        assert "10.1.21.255" == bcast_addr("255.255.255.0", "10.1.21.4")
