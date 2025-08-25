import os
from unittest import mock

import pytest
import yaml

import cloudinit.net
import cloudinit.net.network_state
from tests.unittests.helpers import dir2dict, readResource

SAMPLE_FREEBSD_IFCONFIG_OUT = readResource("netinfo/freebsd-ifconfig-output")
V1 = """
config:
-   id: eno1
    mac_address: 08:94:ef:51:ae:e0
    mtu: 1470
    name: eno1
    subnets:
    -   address: 172.20.80.129/25
        type: static
    type: physical
-   id: eno2
    mac_address: 08:94:ef:51:ae:e1
    mtu: 1470
    name: eno2
    subnets:
    -   address: fd12:3456:789a:1::1/64
        type: static6
    type: physical
version: 1
"""


class TestInterfacesByMac:
    @mock.patch("cloudinit.subp.subp")
    @mock.patch("cloudinit.util.is_FreeBSD")
    def test_get_interfaces_by_mac(self, mock_is_FreeBSD, mock_subp):
        mock_is_FreeBSD.return_value = True
        mock_subp.return_value = (SAMPLE_FREEBSD_IFCONFIG_OUT, 0)
        a = cloudinit.net.get_interfaces_by_mac()
        assert a == {
            "52:54:00:50:b7:0d": "vtnet0",
            "80:00:73:63:5c:48": "re0.33",
            "02:14:39:0e:25:00": "bridge0",
            "02:ff:60:8c:f3:72": "vnet0:11",
        }


@pytest.mark.usefixtures("fake_filesystem")
class TestFreeBSDRoundTrip:
    def _render_and_read(self, ns):
        os.mkdir("/etc")
        with open("/etc/rc.conf", "a") as fd:
            fd.write("# dummy rc.conf\n")
        with open("/etc/resolv.conf", "a") as fd:
            fd.write("# dummy resolv.conf\n")

        renderer = cloudinit.net.freebsd.Renderer()
        renderer.render_network_state(ns)
        return dir2dict("/")

    @mock.patch(
        "cloudinit.subp.subp", return_value=(SAMPLE_FREEBSD_IFCONFIG_OUT, 0)
    )
    @mock.patch("cloudinit.util.is_FreeBSD", return_value=True)
    def test_render_output_has_yaml(self, m_is_freebsd, m_subp):
        entry = {
            "yaml": V1,
        }
        network_config = yaml.safe_load(entry["yaml"])
        ns = cloudinit.net.network_state.parse_net_config_data(network_config)
        files = self._render_and_read(ns)
        assert files == {
            "etc/resolv.conf": "# dummy resolv.conf\n",
            "etc/rc.conf": (
                "# dummy rc.conf\n"
                "ifconfig_eno1="
                "'inet 172.20.80.129 netmask 255.255.255.128 mtu 1470'\n"
                "ifconfig_eno2_ipv6="
                "'inet6 fd12:3456:789a:1::1/64 mtu 1470'\n"
            ),
        }
