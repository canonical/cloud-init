# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import safeyaml
from cloudinit.net import network_state, networkd

V2_CONFIG_SET_NAME = """\
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

V2_CONFIG_SET_NAME_RENDERED_ETH0 = """[Match]
MACAddress=00:11:22:33:44:55
Name=eth0

[Network]
DHCP=no
DNS=8.8.8.8
Domains=spam.local eggs.local

"""

V2_CONFIG_SET_NAME_RENDERED_ETH1 = """[Match]
MACAddress=66:77:88:99:00:11
Name=ens92

[Network]
DHCP=no
DNS=4.4.4.4
Domains=foo.local bar.local

"""


class TestNetworkdRenderState:
    def _parse_network_state_from_config(self, config):
        yaml = safeyaml.load(config)
        return network_state.parse_net_config_data(yaml["network"])

    def test_networkd_render_with_set_name(self):
        ns = self._parse_network_state_from_config(V2_CONFIG_SET_NAME)
        renderer = networkd.Renderer()
        rendered_content = renderer._render_content(ns)

        assert "eth0" in rendered_content
        assert rendered_content["eth0"] == V2_CONFIG_SET_NAME_RENDERED_ETH0
        assert "ens92" in rendered_content
        assert rendered_content["ens92"] == V2_CONFIG_SET_NAME_RENDERED_ETH1


# vi: ts=4 expandtab
