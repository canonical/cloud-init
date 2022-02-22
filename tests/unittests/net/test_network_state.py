# This file is part of cloud-init. See LICENSE file for license information.
import ipaddress
from unittest import mock

import pytest

from cloudinit import safeyaml
from cloudinit.net import network_state
from tests.unittests.helpers import CiTestCase

netstate_path = "cloudinit.net.network_state"


_V1_CONFIG_NAMESERVERS = """\
network:
  version: 1
  config:
    - type: nameserver
      interface: {iface}
      address:
        - 192.168.1.1
        - 8.8.8.8
      search:
        - spam.local
    - type: nameserver
      address:
        - 192.168.1.0
        - 4.4.4.4
      search:
        - eggs.local
    - type: physical
      name: eth0
      mac_address: '00:11:22:33:44:55'
    - type: physical
      name: eth1
      mac_address: '66:77:88:99:00:11'
"""

V1_CONFIG_NAMESERVERS_VALID = _V1_CONFIG_NAMESERVERS.format(iface="eth1")
V1_CONFIG_NAMESERVERS_INVALID = _V1_CONFIG_NAMESERVERS.format(iface="eth90")

V2_CONFIG_NAMESERVERS = """\
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: '00:11:22:33:44:55'
      nameservers:
        search: [spam.local, eggs.local]
        addresses: [8.8.8.8]
    eth1:
      match:
        macaddress: '66:77:88:99:00:11'
      set-name: "ens92"
      nameservers:
        search: [foo.local, bar.local]
        addresses: [4.4.4.4]
"""


class TestNetworkStateParseConfig(CiTestCase):
    def setUp(self):
        super(TestNetworkStateParseConfig, self).setUp()
        nsi_path = netstate_path + ".NetworkStateInterpreter"
        self.add_patch(nsi_path, "m_nsi")

    def test_missing_version_returns_none(self):
        ncfg = {}
        with self.assertRaises(RuntimeError):
            network_state.parse_net_config_data(ncfg)

    def test_unknown_versions_returns_none(self):
        ncfg = {"version": 13.2}
        with self.assertRaises(RuntimeError):
            network_state.parse_net_config_data(ncfg)

    def test_version_2_passes_self_as_config(self):
        ncfg = {"version": 2, "otherconfig": {}, "somemore": [1, 2, 3]}
        network_state.parse_net_config_data(ncfg)
        self.assertEqual(
            [mock.call(version=2, config=ncfg)], self.m_nsi.call_args_list
        )

    def test_valid_config_gets_network_state(self):
        ncfg = {"version": 2, "otherconfig": {}, "somemore": [1, 2, 3]}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)

    def test_empty_v1_config_gets_network_state(self):
        ncfg = {"version": 1, "config": []}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)

    def test_empty_v2_config_gets_network_state(self):
        ncfg = {"version": 2}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)


class TestNetworkStateParseConfigV2(CiTestCase):
    def test_version_2_ignores_renderer_key(self):
        ncfg = {"version": 2, "renderer": "networkd", "ethernets": {}}
        nsi = network_state.NetworkStateInterpreter(
            version=ncfg["version"], config=ncfg
        )
        nsi.parse_config(skip_broken=False)
        self.assertEqual(ncfg, nsi.as_dict()["config"])


class TestNetworkStateParseNameservers:
    def _parse_network_state_from_config(self, config):
        yaml = safeyaml.load(config)
        return network_state.parse_net_config_data(yaml["network"])

    def test_v1_nameservers_valid(self):
        config = self._parse_network_state_from_config(
            V1_CONFIG_NAMESERVERS_VALID
        )

        # If an interface was specified, DNS shouldn't be in the global list
        assert ["192.168.1.0", "4.4.4.4"] == sorted(config.dns_nameservers)
        assert ["eggs.local"] == config.dns_searchdomains

        # If an interface was specified, DNS should be part of the interface
        for iface in config.iter_interfaces():
            if iface["name"] == "eth1":
                assert iface["dns"]["addresses"] == ["192.168.1.1", "8.8.8.8"]
                assert iface["dns"]["search"] == ["spam.local"]
            else:
                assert "dns" not in iface

    def test_v1_nameservers_invalid(self):
        with pytest.raises(ValueError):
            self._parse_network_state_from_config(
                V1_CONFIG_NAMESERVERS_INVALID
            )

    def test_v2_nameservers(self):
        config = self._parse_network_state_from_config(V2_CONFIG_NAMESERVERS)

        # Ensure DNS defined on interface exists on interface
        for iface in config.iter_interfaces():
            if iface["name"] == "eth0":
                assert iface["dns"] == {
                    "nameservers": ["8.8.8.8"],
                    "search": ["spam.local", "eggs.local"],
                }
            else:
                assert iface["dns"] == {
                    "nameservers": ["4.4.4.4"],
                    "search": ["foo.local", "bar.local"],
                }

        # Ensure DNS defined on interface also exists globally (since there
        # is no global DNS definitions in v2)
        assert ["4.4.4.4", "8.8.8.8"] == sorted(config.dns_nameservers)
        assert [
            "bar.local",
            "eggs.local",
            "foo.local",
            "spam.local",
        ] == sorted(config.dns_searchdomains)


class TestNetworkStateHelperFunctions(CiTestCase):
    def test_mask_to_net_prefix_ipv4(self):
        netmask_value = "255.255.255.0"
        expected = 24
        prefix_value = network_state.ipv4_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected

    def test_mask_to_net_prefix_all_bits_ipv4(self):
        netmask_value = "255.255.255.255"
        expected = 32
        prefix_value = network_state.ipv4_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected

    def test_mask_to_net_prefix_to_many_bits_ipv4(self):
        netmask_value = "33"
        self.assertRaises(
            ValueError, network_state.ipv4_mask_to_net_prefix, netmask_value
        )

    def test_mask_to_net_prefix_all_bits_ipv6(self):
        netmask_value = "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
        expected = 128
        prefix_value = network_state.ipv6_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected

    def test_mask_to_net_prefix_ipv6(self):
        netmask_value = "ffff:ffff:ffff:ffff::"
        expected = 64
        prefix_value = network_state.ipv6_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected

    def test_mask_to_net_prefix_raises_value_error(self):
        netmask_value = "ff:ff:ff:ff::"
        self.assertRaises(
            ValueError, network_state.ipv6_mask_to_net_prefix, netmask_value
        )

    def test_mask_to_net_prefix_to_many_bits_ipv6(self):
        netmask_value = "129"
        self.assertRaises(
            ValueError, network_state.ipv6_mask_to_net_prefix, netmask_value
        )

    def test_mask_to_net_prefix_ipv4_object(self):
        netmask_value = ipaddress.IPv4Address("255.255.255.255")
        expected = 32
        prefix_value = network_state.ipv4_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected

    def test_mask_to_net_prefix_ipv6_object(self):
        netmask_value = ipaddress.IPv6Address("ffff:ffff:ffff::")
        expected = 48
        prefix_value = network_state.ipv6_mask_to_net_prefix(netmask_value)
        assert prefix_value == expected


# vi: ts=4 expandtab
