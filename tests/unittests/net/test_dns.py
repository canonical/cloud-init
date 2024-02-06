# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

from cloudinit import safeyaml
from cloudinit.net import network_state


class TestNetDns:
    @mock.patch("cloudinit.net.network_state.get_interfaces_by_mac")
    @mock.patch("cloudinit.net.get_interfaces_by_mac")
    def test_system_mac_address_does_not_break_dns_parsing(
        self, by_mac_state, by_mac_init
    ):
        by_mac_state.return_value = {"00:11:22:33:44:55": "foobar"}
        by_mac_init.return_value = {"00:11:22:33:44:55": "foobar"}
        state = network_state.parse_net_config_data(
            safeyaml.load(
                """\
version: 2
ethernets:
  eth:
    match:
      macaddress: '00:11:22:33:44:55'
    addresses: [10.0.0.2/24]
    gateway4: 10.0.0.1
    nameservers:
      addresses: [10.0.0.3]
"""
            )
        )
        assert (
            "10.0.0.3" in next(state.iter_interfaces())["dns"]["nameservers"]
        )
