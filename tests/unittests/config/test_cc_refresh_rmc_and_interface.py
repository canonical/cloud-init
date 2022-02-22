import logging
from textwrap import dedent

from cloudinit import util
from cloudinit.config import cc_refresh_rmc_and_interface as ccrmci
from tests.unittests import helpers as t_help
from tests.unittests.helpers import mock

LOG = logging.getLogger(__name__)
MPATH = "cloudinit.config.cc_refresh_rmc_and_interface"
NET_INFO = {
    "lo": {
        "ipv4": [
            {
                "ip": "127.0.0.1",
                "bcast": "",
                "mask": "255.0.0.0",
                "scope": "host",
            }
        ],
        "ipv6": [{"ip": "::1/128", "scope6": "host"}],
        "hwaddr": "",
        "up": "True",
    },
    "env2": {
        "ipv4": [
            {
                "ip": "8.0.0.19",
                "bcast": "8.0.0.255",
                "mask": "255.255.255.0",
                "scope": "global",
            }
        ],
        "ipv6": [{"ip": "fe80::f896:c2ff:fe81:8220/64", "scope6": "link"}],
        "hwaddr": "fa:96:c2:81:82:20",
        "up": "True",
    },
    "env3": {
        "ipv4": [
            {
                "ip": "90.0.0.14",
                "bcast": "90.0.0.255",
                "mask": "255.255.255.0",
                "scope": "global",
            }
        ],
        "ipv6": [{"ip": "fe80::f896:c2ff:fe81:8221/64", "scope6": "link"}],
        "hwaddr": "fa:96:c2:81:82:21",
        "up": "True",
    },
    "env4": {
        "ipv4": [
            {
                "ip": "9.114.23.7",
                "bcast": "9.114.23.255",
                "mask": "255.255.255.0",
                "scope": "global",
            }
        ],
        "ipv6": [{"ip": "fe80::f896:c2ff:fe81:8222/64", "scope6": "link"}],
        "hwaddr": "fa:96:c2:81:82:22",
        "up": "True",
    },
    "env5": {
        "ipv4": [],
        "ipv6": [{"ip": "fe80::9c26:c3ff:fea4:62c8/64", "scope6": "link"}],
        "hwaddr": "42:20:86:df:fa:4c",
        "up": "True",
    },
}


class TestRsctNodeFile(t_help.CiTestCase):
    def test_disable_ipv6_interface(self):
        """test parsing of iface files."""
        fname = self.tmp_path("iface-eth5")
        util.write_file(
            fname,
            dedent(
                """\
            BOOTPROTO=static
            DEVICE=eth5
            HWADDR=42:20:86:df:fa:4c
            IPV6INIT=yes
            IPADDR6=fe80::9c26:c3ff:fea4:62c8/64
            IPV6ADDR=fe80::9c26:c3ff:fea4:62c8/64
            NM_CONTROLLED=yes
            ONBOOT=yes
            STARTMODE=auto
            TYPE=Ethernet
            USERCTL=no
            """
            ),
        )

        ccrmci.disable_ipv6(fname)
        self.assertEqual(
            dedent(
                """\
            BOOTPROTO=static
            DEVICE=eth5
            HWADDR=42:20:86:df:fa:4c
            ONBOOT=yes
            STARTMODE=auto
            TYPE=Ethernet
            USERCTL=no
            NM_CONTROLLED=no
            """
            ),
            util.load_file(fname),
        )

    @mock.patch(MPATH + ".refresh_rmc")
    @mock.patch(MPATH + ".restart_network_manager")
    @mock.patch(MPATH + ".disable_ipv6")
    @mock.patch(MPATH + ".refresh_ipv6")
    @mock.patch(MPATH + ".netinfo.netdev_info")
    @mock.patch(MPATH + ".subp.which")
    def test_handle(
        self,
        m_refresh_rmc,
        m_netdev_info,
        m_refresh_ipv6,
        m_disable_ipv6,
        m_restart_nm,
        m_which,
    ):
        """Basic test of handle."""
        m_netdev_info.return_value = NET_INFO
        m_which.return_value = "/opt/rsct/bin/rmcctrl"
        ccrmci.handle("refresh_rmc_and_interface", None, None, None, None)
        self.assertEqual(1, m_netdev_info.call_count)
        m_refresh_ipv6.assert_called_with("env5")
        m_disable_ipv6.assert_called_with(
            "/etc/sysconfig/network-scripts/ifcfg-env5"
        )
        self.assertEqual(1, m_restart_nm.call_count)
        self.assertEqual(1, m_refresh_rmc.call_count)

    @mock.patch(MPATH + ".netinfo.netdev_info")
    def test_find_ipv6(self, m_netdev_info):
        """find_ipv6_ifaces parses netdev_info returning those with ipv6"""
        m_netdev_info.return_value = NET_INFO
        found = ccrmci.find_ipv6_ifaces()
        self.assertEqual(["env5"], found)

    @mock.patch(MPATH + ".subp.subp")
    def test_refresh_ipv6(self, m_subp):
        """refresh_ipv6 should ip down and up the interface."""
        iface = "myeth0"
        ccrmci.refresh_ipv6(iface)
        m_subp.assert_has_calls(
            [
                mock.call(["ip", "link", "set", iface, "down"]),
                mock.call(["ip", "link", "set", iface, "up"]),
            ]
        )
