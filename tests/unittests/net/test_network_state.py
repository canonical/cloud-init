# This file is part of cloud-init. See LICENSE file for license information.
import ipaddress
from unittest import mock

import pytest
import yaml

from cloudinit import util
from cloudinit.net import network_state
from cloudinit.net.netplan import Renderer as NetplanRenderer
from cloudinit.net.renderers import NAME_TO_RENDERER
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
            [mock.call(version=2, config=ncfg, renderer=None)],
            self.m_nsi.call_args_list,
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


@mock.patch("cloudinit.net.network_state.get_interfaces_by_mac")
class TestNetworkStateParseConfigV2:
    def test_version_2_ignores_renderer_key(self, m_get_interfaces_by_mac):
        ncfg = {"version": 2, "renderer": "networkd", "ethernets": {}}
        nsi = network_state.NetworkStateInterpreter(
            version=ncfg["version"], config=ncfg
        )
        nsi.parse_config(skip_broken=False)
        assert ncfg == nsi.as_dict()["config"]

    @pytest.mark.parametrize(
        "cfg",
        [
            pytest.param(
                """
                version: 2
                ethernets:
                    eth0:
                        addresses:
                        - 10.54.2.19/21
                        - 2a00:1730:fff9:100::52/128
                        {gateway4}
                        {gateway6}
                        match:
                            macaddress: 52:54:00:3f:fc:f7
                        nameservers:
                            addresses:
                            - 10.52.1.1
                            - 10.52.1.71
                            - 2001:4860:4860::8888
                            - 2001:4860:4860::8844
                        set-name: eth0
                """,
                id="ethernets",
            ),
            pytest.param(
                """
                version: 2
                vlans:
                  encc000.2653:
                    id: 2653
                    link: "encc000"
                    addresses:
                      - 10.54.2.19/21
                      - 2a00:1730:fff9:100::52/128
                    {gateway4}
                    {gateway6}
                    nameservers:
                      addresses:
                        - 10.52.1.1
                        - 10.52.1.71
                        - 2001:4860:4860::8888
                        - 2001:4860:4860::8844
                """,
                id="vlan",
            ),
            pytest.param(
                """
                version: 2
                bonds:
                  bond0:
                    addresses:
                      - 10.54.2.19/21
                      - 2a00:1730:fff9:100::52/128
                    {gateway4}
                    {gateway6}
                    interfaces:
                    - enp0s0
                    - enp0s1
                    mtu: 1334
                    parameters: {{}}
                """,
                id="bond",
            ),
            pytest.param(
                """
                version: 2
                bridges:
                  bridge0:
                    addresses:
                      - 10.54.2.19/21
                      - 2a00:1730:fff9:100::52/128
                    {gateway4}
                    {gateway6}
                    interfaces:
                    - enp0s0
                    - enp0s1
                    parameters: {{}}
                """,
                id="bridge",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "renderer_cls",
        [
            pytest.param(None, id="non-netplan"),
        ]
        + [
            pytest.param(mod.Renderer, id=name)
            for name, mod in NAME_TO_RENDERER.items()
        ],
    )
    def test_v2_warns_deprecated_gateways(
        self, m_get_interfaces_by_mac, renderer_cls, cfg: str, caplog
    ):
        """
        Tests that a v2 netconf with the deprecated `gateway4` or `gateway6`
        issues a warning about it only on non netplan targets.

        In netplan targets we perform a passthrough and the warning is not
        needed.
        """
        util.deprecate.__dict__["log"] = set()
        ncfg = yaml.safe_load(
            cfg.format(
                gateway4="gateway4: 10.54.0.1",
                gateway6="gateway6: 2a00:1730:fff9:100::1",
            )
        )
        nsi = network_state.NetworkStateInterpreter(
            version=ncfg["version"],
            config=ncfg,
            renderer=mock.MagicMock(spec=renderer_cls),
        )
        nsi.parse_config(skip_broken=False)
        assert ncfg == nsi.as_dict()["config"]

        if renderer_cls != NetplanRenderer:
            count = 1  # Only one deprecation
        else:
            count = 0  # No deprecation as we passthrough
        assert count == caplog.text.count(
            "The use of `gateway4` and `gateway6`"
        )


class TestNetworkStateParseNameservers:
    def _parse_network_state_from_config(self, config):
        with mock.patch("cloudinit.net.network_state.get_interfaces_by_mac"):
            config = yaml.safe_load(config)
            return network_state.parse_net_config_data(config["network"])

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
                assert iface["dns"]["nameservers"] == [
                    "192.168.1.1",
                    "8.8.8.8",
                ]
                assert iface["dns"]["search"] == ["spam.local"]
            else:
                assert "dns" not in iface

    def test_v1_nameservers_invalid(self):
        with pytest.raises(ValueError):
            self._parse_network_state_from_config(
                V1_CONFIG_NAMESERVERS_INVALID
            )

    def test_v2_nameservers(self, mocker):
        mocker.patch("cloudinit.net.network_state.get_interfaces_by_mac")
        mocker.patch("cloudinit.net.get_interfaces_by_mac")
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

        # Ensure DNS defined on interface does not exist globally
        for server in ["4.4.4.4", "8.8.8.8"]:
            assert server not in config.dns_nameservers
        for search in ["bar.local", "eggs.local", "foo.local", "spam.local"]:
            assert search not in config.dns_searchdomains


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
