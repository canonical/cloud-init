# This file is part of cloud-init. See LICENSE file for license information.

from configparser import ConfigParser
from string import Template
from unittest import mock

import pytest
import yaml

from cloudinit import safeyaml
from cloudinit.net import network_state, networkd

V2_CONFIG_OPTIONAL = """\
network:
  version: 2
  ethernets:
    eth0:
      optional: true
    eth1:
      optional: false
"""

V2_CONFIG_OPTIONAL_RENDERED_ETH0 = """[Link]
RequiredForOnline=no

[Match]
Name=eth0

[Network]
DHCP=no

"""

V2_CONFIG_OPTIONAL_RENDERED_ETH1 = """[Match]
Name=eth1

[Network]
DHCP=no

"""

V2_CONFIG_SET_NAME = """\
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: '00:11:22:33:44:55'
      addresses: [172.16.10.2/12, 172.16.10.3/12]
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

V2_CONFIG_SET_NAME_RENDERED_ETH0 = """[Address]
Address=172.16.10.2/12

[Address]
Address=172.16.10.3/12

[Match]
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

V2_CONFIG_DHCP_YES_OVERRIDES = """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      dhcp4-overrides:
        hostname: hal
        route-metric: 1100
        send-hostname: false
        use-dns: false
        use-domains: false
        use-hostname: false
        use-mtu: false
        use-ntp: false
        use-routes: false
      dhcp6: true
      dhcp6-overrides:
        use-dns: false
        use-domains: false
        use-hostname: false
        use-ntp: false
      match:
        macaddress: "00:11:22:33:44:55"
      nameservers:
        addresses: ["8.8.8.8", "2001:4860:4860::8888"]
"""

V2_CONFIG_DHCP_YES_OVERRIDES_RENDERED = """[DHCPv4]
Hostname=hal
RouteMetric=1100
SendHostname=False
UseDNS=False
UseDomains=False
UseHostname=False
UseMTU=False
UseNTP=False
UseRoutes=False

[DHCPv6]
UseDNS=False
UseDomains=False
UseHostname=False
UseNTP=False

[Match]
MACAddress=00:11:22:33:44:55
Name=eth0

[Network]
DHCP=yes
DNS=8.8.8.8 2001:4860:4860::8888

"""

V2_CONFIG_DHCP_DOMAIN_VS_OVERRIDE = Template(
    """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp${dhcp_version}domain: true
      dhcp${dhcp_version}: true
      dhcp${dhcp_version}-overrides:
        use-domains: route
"""
)

V2_CONFIG_DHCP_OVERRIDES = Template(
    """\
network:
  version: 2
  ethernets:
    eth0:
      dhcp${dhcp_version}: true
      dhcp${dhcp_version}-overrides:
        ${key}: ${value}
      match:
        macaddress: "00:11:22:33:44:55"
      nameservers:
        addresses: ["8.8.8.8", "2001:4860:4860::8888"]
"""
)

V2_CONFIG_DHCP_OVERRIDES_RENDERED = Template(
    """[DHCPv${dhcp_version}]
${key}=${value}

[Match]
MACAddress=00:11:22:33:44:55
Name=eth0

[Network]
DHCP=ipv${dhcp_version}
DNS=8.8.8.8 2001:4860:4860::8888

"""
)

V1_CONFIG_MULTI_SUBNETS = """
network:
  version: 1
  config:
    - type: physical
      name: eth0
      mac_address: 'ae:98:25:fa:36:9e'
      subnets:
      - type: static
        address: '10.0.0.2'
        netmask: '255.255.255.255'
        gateway: '10.0.0.1'
      - type: static6
        address: '2a01:4f8:10a:19d2::4/64'
        gateway: '2a01:4f8:10a:19d2::2'
    - type: nameserver
      address:
      - '100.100.100.100'
      search:
      - 'rgrunbla.github.beta.tailscale.net'
"""

V1_CONFIG_MULTI_SUBNETS_RENDERED = """\
[Address]
Address=10.0.0.2/32

[Address]
Address=2a01:4f8:10a:19d2::4/64

[Match]
MACAddress=ae:98:25:fa:36:9e
Name=eth0

[Network]
DHCP=no
DNS=100.100.100.100
Domains=rgrunbla.github.beta.tailscale.net

[Route]
Gateway=10.0.0.1
GatewayOnLink=yes

[Route]
Gateway=2a01:4f8:10a:19d2::2

"""

V2_CONFIG_MULTI_SUBNETS = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.1/24
        - fec0::1/64
      gateway4: 192.168.254.254
      gateway6: "fec0::ffff"
      routes:
        - to: 169.254.1.1/32
        - to: "fe80::1/128"
"""

V2_CONFIG_MULTI_SUBNETS_RENDERED = """\
[Address]
Address=192.168.1.1/24

[Address]
Address=fec0::1/64

[Match]
Name=eth0

[Network]
DHCP=no

[Route]
Gateway=192.168.254.254
GatewayOnLink=yes

[Route]
Gateway=fec0::ffff

[Route]
Destination=169.254.1.1/32

[Route]
Destination=fe80::1/128

"""

V1_CONFIG_MULTI_SUBNETS_NOT_ONLINK = """
network:
  version: 1
  config:
    - type: physical
      name: eth0
      mac_address: 'ae:98:25:fa:36:9e'
      subnets:
      - type: static
        address: '10.0.0.2'
        netmask: '255.255.255.0'
        gateway: '10.0.0.1'
      - type: static6
        address: '2a01:4f8:10a:19d2::4/64'
        gateway: '2a01:4f8:10a:19d2::2'
    - type: nameserver
      address:
      - '100.100.100.100'
      search:
      - 'rgrunbla.github.beta.tailscale.net'
"""

V1_CONFIG_MULTI_SUBNETS_NOT_ONLINK_RENDERED = """\
[Address]
Address=10.0.0.2/24

[Address]
Address=2a01:4f8:10a:19d2::4/64

[Match]
MACAddress=ae:98:25:fa:36:9e
Name=eth0

[Network]
DHCP=no
DNS=100.100.100.100
Domains=rgrunbla.github.beta.tailscale.net

[Route]
Gateway=10.0.0.1

[Route]
Gateway=2a01:4f8:10a:19d2::2

"""

V2_CONFIG_MULTI_SUBNETS_NOT_ONLINK = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.1/24
        - fec0::1/64
      gateway4: 192.168.1.254
      gateway6: "fec0::ffff"
      routes:
        - to: 169.254.1.1/32
        - to: "fe80::1/128"
"""

V2_CONFIG_MULTI_SUBNETS_NOT_ONLINK_RENDERED = """\
[Address]
Address=192.168.1.1/24

[Address]
Address=fec0::1/64

[Match]
Name=eth0

[Network]
DHCP=no

[Route]
Gateway=192.168.1.254

[Route]
Gateway=fec0::ffff

[Route]
Destination=169.254.1.1/32

[Route]
Destination=fe80::1/128

"""

V1_CONFIG_MULTI_SUBNETS_ONLINK = """
network:
  version: 1
  config:
    - type: physical
      name: eth0
      mac_address: 'ae:98:25:fa:36:9e'
      subnets:
      - type: static
        address: '10.0.0.2'
        netmask: '255.255.255.0'
        gateway: '192.168.0.1'
      - type: static6
        address: '2a01:4f8:10a:19d2::4/64'
        gateway: '2000:4f8:10a:19d2::2'
    - type: nameserver
      address:
      - '100.100.100.100'
      search:
      - 'rgrunbla.github.beta.tailscale.net'
"""

V1_CONFIG_MULTI_SUBNETS_ONLINK_RENDERED = """\
[Address]
Address=10.0.0.2/24

[Address]
Address=2a01:4f8:10a:19d2::4/64

[Match]
MACAddress=ae:98:25:fa:36:9e
Name=eth0

[Network]
DHCP=no
DNS=100.100.100.100
Domains=rgrunbla.github.beta.tailscale.net

[Route]
Gateway=192.168.0.1
GatewayOnLink=yes

[Route]
Gateway=2000:4f8:10a:19d2::2
GatewayOnLink=yes

"""

V2_CONFIG_MULTI_SUBNETS_ONLINK = """
network:
  version: 2
  ethernets:
    eth0:
      addresses:
        - 192.168.1.1/32
        - fec0::1/128
      gateway4: 192.168.254.254
      gateway6: "fec0::ffff"
      routes:
        - to: 169.254.1.1/32
        - to: "fe80::1/128"
"""

V2_CONFIG_MULTI_SUBNETS_ONLINK_RENDERED = """\
[Address]
Address=192.168.1.1/32

[Address]
Address=fec0::1/128

[Match]
Name=eth0

[Network]
DHCP=no

[Route]
Gateway=192.168.254.254
GatewayOnLink=yes

[Route]
Gateway=fec0::ffff
GatewayOnLink=yes

[Route]
Destination=169.254.1.1/32

[Route]
Destination=fe80::1/128

"""

V1_CONFIG_ACCEPT_RA_YAML = """\
network:
  version: 1
  config:
    - type: physical
      name: eth0
      mac_address: "00:11:22:33:44:55"
"""

V2_CONFIG_ACCEPT_RA_YAML = """\
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: "00:11:22:33:44:55"
"""


class TestNetworkdRenderState:
    def _parse_network_state_from_config(self, config):
        with mock.patch("cloudinit.net.network_state.get_interfaces_by_mac"):
            config = yaml.safe_load(config)
            return network_state.parse_net_config_data(config["network"])

    def test_networkd_render_with_optional(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(V2_CONFIG_OPTIONAL)
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert "eth0" in rendered_content
        assert rendered_content["eth0"] == V2_CONFIG_OPTIONAL_RENDERED_ETH0
        assert "eth1" in rendered_content
        assert rendered_content["eth1"] == V2_CONFIG_OPTIONAL_RENDERED_ETH1

    def test_networkd_render_with_set_name(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(V2_CONFIG_SET_NAME)
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert "eth0" in rendered_content
        assert rendered_content["eth0"] == V2_CONFIG_SET_NAME_RENDERED_ETH0
        assert "ens92" in rendered_content
        assert rendered_content["ens92"] == V2_CONFIG_SET_NAME_RENDERED_ETH1

    def test_networkd_render_dhcp_yes_with_dhcp_overrides(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V2_CONFIG_DHCP_YES_OVERRIDES
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert (
            rendered_content["eth0"] == V2_CONFIG_DHCP_YES_OVERRIDES_RENDERED
        )

    @pytest.mark.parametrize("dhcp_version", [("4"), ("6")])
    def test_networkd_render_dhcp_domains_vs_overrides(self, dhcp_version):
        expected_exception = (
            f"eth0 has both dhcp{dhcp_version}domain and"
            f" dhcp{dhcp_version}-overrides.use-domains configured. Use one"
        )
        with pytest.raises(Exception, match=expected_exception):
            with mock.patch("cloudinit.net.get_interfaces_by_mac"):
                config = V2_CONFIG_DHCP_DOMAIN_VS_OVERRIDE.substitute(
                    dhcp_version=dhcp_version
                )
                ns = self._parse_network_state_from_config(config)
                renderer = networkd.Renderer()
                renderer._render_content(ns)

    @pytest.mark.parametrize(
        "dhcp_version,spec_key,spec_value,rendered_key,rendered_value",
        [
            ("4", "use-dns", "false", "UseDNS", "False"),
            ("4", "use-dns", "true", "UseDNS", "True"),
            ("4", "use-ntp", "false", "UseNTP", "False"),
            ("4", "use-ntp", "true", "UseNTP", "True"),
            ("4", "send-hostname", "false", "SendHostname", "False"),
            ("4", "send-hostname", "true", "SendHostname", "True"),
            ("4", "use-hostname", "false", "UseHostname", "False"),
            ("4", "use-hostname", "true", "UseHostname", "True"),
            ("4", "hostname", "olivaw", "Hostname", "olivaw"),
            ("4", "route-metric", "12345", "RouteMetric", "12345"),
            ("4", "use-domains", "false", "UseDomains", "False"),
            ("4", "use-domains", "true", "UseDomains", "True"),
            ("4", "use-domains", "route", "UseDomains", "route"),
            ("4", "use-mtu", "false", "UseMTU", "False"),
            ("4", "use-mtu", "true", "UseMTU", "True"),
            ("4", "use-routes", "false", "UseRoutes", "False"),
            ("4", "use-routes", "true", "UseRoutes", "True"),
            ("6", "use-dns", "false", "UseDNS", "False"),
            ("6", "use-dns", "true", "UseDNS", "True"),
            ("6", "use-ntp", "false", "UseNTP", "False"),
            ("6", "use-ntp", "true", "UseNTP", "True"),
            ("6", "use-hostname", "false", "UseHostname", "False"),
            ("6", "use-hostname", "true", "UseHostname", "True"),
            ("6", "use-domains", "false", "UseDomains", "False"),
            ("6", "use-domains", "true", "UseDomains", "True"),
            ("6", "use-domains", "route", "UseDomains", "route"),
        ],
    )
    def test_networkd_render_dhcp_overrides(
        self, dhcp_version, spec_key, spec_value, rendered_key, rendered_value
    ):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V2_CONFIG_DHCP_OVERRIDES.substitute(
                    dhcp_version=dhcp_version, key=spec_key, value=spec_value
                )
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert rendered_content[
            "eth0"
        ] == V2_CONFIG_DHCP_OVERRIDES_RENDERED.substitute(
            dhcp_version=dhcp_version, key=rendered_key, value=rendered_value
        )

    def test_networkd_render_v1_multi_subnets(self):
        """
        Ensure a device with multiple subnets gets correctly rendered.

        Per systemd-networkd docs, [Address] can only contain a single instance
        of Address.
        """
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(V1_CONFIG_MULTI_SUBNETS)
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert rendered_content["eth0"] == V1_CONFIG_MULTI_SUBNETS_RENDERED

    def test_networkd_render_v2_multi_subnets(self):
        """
        Ensure a device with multiple subnets gets correctly rendered.

        Per systemd-networkd docs, [Route] can only contain a single instance
        of Gateway.
        """
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(V2_CONFIG_MULTI_SUBNETS)
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert rendered_content["eth0"] == V2_CONFIG_MULTI_SUBNETS_RENDERED

    def test_networkd_render_v1_multi_subnets_not_onlink(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V1_CONFIG_MULTI_SUBNETS_NOT_ONLINK
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert (
            rendered_content["eth0"]
            == V1_CONFIG_MULTI_SUBNETS_NOT_ONLINK_RENDERED
        )

    def test_networkd_render_v2_multi_subnets_not_onlink(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V2_CONFIG_MULTI_SUBNETS_NOT_ONLINK
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert (
            rendered_content["eth0"]
            == V2_CONFIG_MULTI_SUBNETS_NOT_ONLINK_RENDERED
        )

    def test_networkd_render_v1_multi_subnets_onlink(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V1_CONFIG_MULTI_SUBNETS_ONLINK
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert (
            rendered_content["eth0"] == V1_CONFIG_MULTI_SUBNETS_ONLINK_RENDERED
        )

    def test_networkd_render_v2_multi_subnets_onlink(self):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            ns = self._parse_network_state_from_config(
                V2_CONFIG_MULTI_SUBNETS_ONLINK
            )
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        assert (
            rendered_content["eth0"] == V2_CONFIG_MULTI_SUBNETS_ONLINK_RENDERED
        )

    @pytest.mark.parametrize("version", ["v1", "v2"])
    @pytest.mark.parametrize(
        "address", ["4", "6", "10.0.0.10/24", "2001:db8::1/64"]
    )
    @pytest.mark.parametrize("accept_ra", [True, False, None])
    def test_networkd_render_accept_ra(self, version, address, accept_ra):
        with mock.patch("cloudinit.net.get_interfaces_by_mac"):
            # network-config v1 inputs
            if version == "v1":
                config = yaml.safe_load(V1_CONFIG_ACCEPT_RA_YAML)
                if address == "4" or address == "6":
                    config["network"]["config"][0]["subnets"] = [
                        {"type": f"dhcp{address}"}
                    ]
                else:
                    config["network"]["config"][0]["subnets"] = [
                        {"type": "static", "address": address}
                    ]
                if accept_ra is not None:
                    config["network"]["config"][0]["accept-ra"] = accept_ra
            # network-config v2 inputs
            elif version == "v2":
                config = yaml.safe_load(V2_CONFIG_ACCEPT_RA_YAML)
                if address == "4" or address == "6":
                    config["network"]["ethernets"]["eth0"][
                        f"dhcp{address}"
                    ] = True
                else:
                    config["network"]["ethernets"]["eth0"]["addresses"] = [
                        address
                    ]
                if isinstance(accept_ra, bool):
                    config["network"]["ethernets"]["eth0"][
                        "accept-ra"
                    ] = accept_ra
            else:
                raise ValueError(f"Unknown network-config version: {version}")
            config = safeyaml.dumps(config)

            # render
            ns = self._parse_network_state_from_config(config)
            renderer = networkd.Renderer()
            rendered_content = renderer._render_content(ns)

        # dump the input/output for debugging test failures
        print(config)
        print(rendered_content["eth0"])

        # validate the rendered content
        c = ConfigParser()
        c.read_string(rendered_content["eth0"])

        if address in ["4", "6"]:
            expected_dhcp = f"ipv{address}"
            expected_address = None
        else:
            expected_dhcp = False
            expected_address = address
        try:
            got_dhcp = c.getboolean("Network", "DHCP")
        except ValueError:
            got_dhcp = c.get("Network", "DHCP", fallback=None)
        got_address = c.get("Address", "Address", fallback=None)
        got_accept_ra = c.getboolean("Network", "IPv6AcceptRA", fallback=None)
        assert (
            got_dhcp == expected_dhcp
        ), f"DHCP={got_dhcp}, expected {expected_dhcp}"
        assert (
            got_address == expected_address
        ), f"Address={got_address}, expected {expected_address}"
        assert (
            got_accept_ra == accept_ra
        ), f"IPv6AcceptRA={got_accept_ra}, expected {accept_ra}"
