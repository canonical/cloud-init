# This file is part of cloud-init. See LICENSE file for license information.
# ./cloudinit/sources/helpers/tests/test_openstack.py
from unittest import mock

from cloudinit.sources.helpers import openstack


@mock.patch(
    "cloudinit.net.is_openvswitch_internal_interface",
    mock.Mock(return_value=False),
)
class TestConvertNetJson:
    def test_phy_types(self):
        """Verify the different known physical types are handled."""
        # network_data.json example from
        # https://docs.openstack.org/nova/latest/user/metadata.html
        mac0 = "fa:16:3e:9c:bf:3d"
        net_json = {
            "links": [
                {
                    "ethernet_mac_address": mac0,
                    "id": "tapcd9f6d46-4a",
                    "mtu": None,
                    "type": "bridge",
                    "vif_id": "cd9f6d46-4a3a-43ab-a466-994af9db96fc",
                }
            ],
            "networks": [
                {
                    "id": "network0",
                    "link": "tapcd9f6d46-4a",
                    "network_id": "99e88329-f20d-4741-9593-25bf07847b16",
                    "type": "ipv4_dhcp",
                }
            ],
            "services": [{"address": "8.8.8.8", "type": "dns"}],
        }
        macs = {mac0: "eth0"}

        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "fa:16:3e:9c:bf:3d",
                    "mtu": None,
                    "name": "eth0",
                    "subnets": [{"type": "dhcp4"}],
                    "type": "physical",
                },
                {"address": "8.8.8.8", "type": "nameserver"},
            ],
        }

        for t in openstack.KNOWN_PHYSICAL_TYPES:
            net_json["links"][0]["type"] = t
            assert expected == openstack.convert_net_json(
                network_json=net_json, known_macs=macs
            )

    def test_subnet_dns(self):
        """Verify the different known physical types are handled."""
        # network_data.json example from
        # https://docs.openstack.org/nova/latest/user/metadata.html
        mac0 = "fa:16:3e:9c:bf:3d"
        net_json = {
            "links": [
                {
                    "ethernet_mac_address": mac0,
                    "id": "tapcd9f6d46-4a",
                    "mtu": None,
                    "type": "phy",
                    "vif_id": "cd9f6d46-4a3a-43ab-a466-994af9db96fc",
                }
            ],
            "networks": [
                {
                    "id": "network0",
                    "link": "tapcd9f6d46-4a",
                    "network_id": "99e88329-f20d-4741-9593-25bf07847b16",
                    "type": "ipv4",
                    "ip_address": "192.168.123.5",
                    "netmask": "255.255.255.0",
                    "services": [{"type": "dns", "address": "192.168.123.1"}],
                }
            ],
        }
        macs = {mac0: "eth0"}

        expected = {
            "version": 1,
            "config": [
                {
                    "mac_address": "fa:16:3e:9c:bf:3d",
                    "mtu": None,
                    "name": "eth0",
                    "subnets": [
                        {
                            "type": "static",
                            "address": "192.168.123.5",
                            "netmask": "255.255.255.0",
                            "ipv4": True,
                            "dns_nameservers": ["192.168.123.1"],
                        }
                    ],
                    "type": "physical",
                }
            ],
        }

        for t in openstack.KNOWN_PHYSICAL_TYPES:
            net_json["links"][0]["type"] = t
            assert expected == openstack.convert_net_json(
                network_json=net_json, known_macs=macs
            )

    def test_bond_mac(self):
        """Verify the bond mac address is assigned correctly."""
        network_json = {
            "links": [
                {
                    "id": "ens1f0np0",
                    "name": "ens1f0np0",
                    "type": "phy",
                    "ethernet_mac_address": "xx:xx:xx:xx:xx:00",
                    "mtu": 9000,
                },
                {
                    "id": "ens1f1np1",
                    "name": "ens1f1np1",
                    "type": "phy",
                    "ethernet_mac_address": "xx:xx:xx:xx:xx:01",
                    "mtu": 9000,
                },
                {
                    "id": "bond0",
                    "name": "bond0",
                    "type": "bond",
                    "bond_links": ["ens1f0np0", "ens1f1np1"],
                    "mtu": 9000,
                    "ethernet_mac_address": "xx:xx:xx:xx:xx:00",
                    "bond_mode": "802.3ad",
                    "bond_xmit_hash_policy": "layer3+4",
                    "bond_miimon": 100,
                },
                {
                    "id": "bond0.123",
                    "name": "bond0.123",
                    "type": "vlan",
                    "vlan_link": "bond0",
                    "vlan_id": 123,
                    "vlan_mac_address": "xx:xx:xx:xx:xx:00",
                },
            ],
            "networks": [
                {
                    "id": "publicnet-ipv4",
                    "type": "ipv4",
                    "link": "bond0.123",
                    "ip_address": "x.x.x.x",
                    "netmask": "255.255.255.0",
                    "routes": [
                        {
                            "network": "0.0.0.0",
                            "netmask": "0.0.0.0",
                            "gateway": "x.x.x.1",
                        }
                    ],
                    "network_id": "00000000-0000-0000-0000-000000000000",
                }
            ],
            "services": [{"type": "dns", "address": "1.1.1.1"}],
        }
        expected = {
            "config": [
                {
                    "mac_address": "xx:xx:xx:xx:xx:00",
                    "mtu": 9000,
                    "name": "ens1f0np0",
                    "subnets": [],
                    "type": "physical",
                },
                {
                    "mac_address": "xx:xx:xx:xx:xx:01",
                    "mtu": 9000,
                    "name": "ens1f1np1",
                    "subnets": [],
                    "type": "physical",
                },
                {
                    "bond_interfaces": ["ens1f0np0", "ens1f1np1"],
                    "mtu": 9000,
                    "name": "bond0",
                    "mac_address": "xx:xx:xx:xx:xx:00",
                    "params": {
                        "bond-miimon": 100,
                        "bond-mode": "802.3ad",
                        "bond-xmit_hash_policy": "layer3+4",
                    },
                    "subnets": [],
                    "type": "bond",
                },
                {
                    "name": "bond0.123",
                    "subnets": [
                        {
                            "address": "x.x.x.x",
                            "ipv4": True,
                            "netmask": "255.255.255.0",
                            "routes": [
                                {
                                    "gateway": "x.x.x.1",
                                    "netmask": "0.0.0.0",
                                    "network": "0.0.0.0",
                                }
                            ],
                            "type": "static",
                        }
                    ],
                    "type": "vlan",
                    "vlan_id": 123,
                    "vlan_link": "bond0",
                },
                {"address": "1.1.1.1", "type": "nameserver"},
            ],
            "version": 1,
        }
        macs = {
            "xx:xx:xx:xx:xx:00": "ens1f0np0",
            "xx:xx:xx:xx:xx:01": "ens1f1np1",
        }
        assert expected == openstack.convert_net_json(
            network_json=network_json, known_macs=macs
        )
