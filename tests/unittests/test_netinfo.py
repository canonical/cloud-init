# This file is part of cloud-init. See LICENSE file for license information.

"""Tests netinfo module functions and classes."""

import json
from copy import copy

import pytest

from cloudinit import subp
from cloudinit.netinfo import (
    _netdev_info_iproute_json,
    netdev_info,
    netdev_pformat,
    route_pformat,
)
from tests.unittests.helpers import mock, readResource

# Example ifconfig and route output
SAMPLE_OLD_IFCONFIG_OUT = readResource("netinfo/old-ifconfig-output")
SAMPLE_NEW_IFCONFIG_OUT = readResource("netinfo/new-ifconfig-output")
SAMPLE_FREEBSD_IFCONFIG_OUT = readResource("netinfo/freebsd-ifconfig-output")
SAMPLE_IPADDRSHOW_OUT = readResource("netinfo/sample-ipaddrshow-output")
SAMPLE_IPADDRSHOW_JSON = readResource("netinfo/sample-ipaddrshow-json")
SAMPLE_ROUTE_OUT_V4 = readResource("netinfo/sample-route-output-v4")
SAMPLE_ROUTE_OUT_V6 = readResource("netinfo/sample-route-output-v6")
SAMPLE_IPROUTE_OUT_V4 = readResource("netinfo/sample-iproute-output-v4")
SAMPLE_IPROUTE_OUT_V6 = readResource("netinfo/sample-iproute-output-v6")
NETDEV_FORMATTED_OUT = readResource("netinfo/netdev-formatted-output")
ROUTE_FORMATTED_OUT = readResource("netinfo/route-formatted-output")
FREEBSD_NETDEV_OUT = readResource("netinfo/freebsd-netdev-formatted-output")


class TestNetInfo:
    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_old_nettools_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering old nettools info."""
        m_subp.return_value = (SAMPLE_OLD_IFCONFIG_OUT, "")
        m_which.side_effect = lambda x: x if x == "ifconfig" else None
        content = netdev_pformat()
        assert NETDEV_FORMATTED_OUT == content

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_new_nettools_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering netdev new nettools info."""
        m_subp.return_value = (SAMPLE_NEW_IFCONFIG_OUT, "")
        m_which.side_effect = lambda x: x if x == "ifconfig" else None
        content = netdev_pformat()
        assert NETDEV_FORMATTED_OUT == content

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_freebsd_nettools_pformat(self, m_subp, m_which):
        """netdev_pformat properly rendering netdev new nettools info."""
        m_subp.return_value = (SAMPLE_FREEBSD_IFCONFIG_OUT, "")
        m_which.side_effect = lambda x: x if x == "ifconfig" else None
        content = netdev_pformat()
        print()
        print(content)
        print()
        assert FREEBSD_NETDEV_OUT == content

    @pytest.mark.parametrize(
        "resource,is_json",
        [(SAMPLE_IPADDRSHOW_OUT, False), (SAMPLE_IPADDRSHOW_JSON, True)],
    )
    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_iproute_pformat(self, m_subp, m_which, resource, is_json):
        """netdev_pformat properly rendering ip route info (non json)."""
        m_subp.return_value = (resource, "")
        if not is_json:
            m_subp.side_effect = [subp.ProcessExecutionError, (resource, "")]
        m_which.side_effect = lambda x: x if x == "ip" else None
        content = netdev_pformat()
        new_output = copy(NETDEV_FORMATTED_OUT)
        # ip route show describes global scopes on ipv4 addresses
        # whereas ifconfig does not. Add proper global/host scope to output.
        new_output = new_output.replace("|   .    | 50:7b", "| global | 50:7b")
        new_output = new_output.replace(
            "255.0.0.0   |   .    |", "255.0.0.0   |  host  |"
        )
        assert new_output == content

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_warn_on_missing_commands(self, m_subp, m_which, caplog):
        """netdev_pformat warns when missing both ip and 'netstat'."""
        m_which.return_value = None  # Niether ip nor netstat found
        content = netdev_pformat()
        assert "\n" == content
        log = caplog.records[0]
        assert log.levelname == "WARNING"
        assert log.msg == (
            "Could not print networks: missing 'ip' and 'ifconfig' commands"
        )
        m_subp.assert_not_called()

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_info_nettools_down(self, m_subp, m_which):
        """test netdev_info using nettools and down interfaces."""
        m_subp.return_value = (
            readResource("netinfo/new-ifconfig-output-down"),
            "",
        )
        m_which.side_effect = lambda x: x if x == "ifconfig" else None
        assert netdev_info(".") == {
            "eth0": {
                "ipv4": [],
                "ipv6": [],
                "hwaddr": "00:16:3e:de:51:a6",
                "up": False,
            },
            "lo": {
                "ipv4": [{"ip": "127.0.0.1", "mask": "255.0.0.0"}],
                "ipv6": [{"ip": "::1/128", "scope6": "host"}],
                "hwaddr": ".",
                "up": True,
            },
        }

    @pytest.mark.parametrize(
        "resource,is_json",
        [
            ("netinfo/sample-ipaddrshow-output-down", False),
            ("netinfo/sample-ipaddrshow-json-down", True),
        ],
    )
    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_netdev_info_iproute_down(
        self, m_subp, m_which, resource, is_json
    ):
        """Test netdev_info with ip and down interfaces."""
        m_subp.return_value = (readResource(resource), "")
        if not is_json:
            m_subp.side_effect = [
                subp.ProcessExecutionError,
                (readResource(resource), ""),
            ]
        m_which.side_effect = lambda x: x if x == "ip" else None
        assert netdev_info(".") == {
            "lo": {
                "ipv4": [
                    {
                        "ip": "127.0.0.1",
                        "bcast": ".",
                        "mask": "255.0.0.0",
                        "scope": "host",
                    }
                ],
                "ipv6": [{"ip": "::1/128", "scope6": "host"}],
                "hwaddr": ".",
                "up": True,
            },
            "eth0": {
                "ipv4": [],
                "ipv6": [],
                "hwaddr": "00:16:3e:de:51:a6",
                "up": False,
            },
        }

    @mock.patch("cloudinit.netinfo.netdev_info")
    def test_netdev_pformat_with_down(self, m_netdev_info):
        """test netdev_pformat when netdev_info returns 'down' interfaces."""
        m_netdev_info.return_value = {
            "lo": {
                "ipv4": [
                    {"ip": "127.0.0.1", "mask": "255.0.0.0", "scope": "host"}
                ],
                "ipv6": [{"ip": "::1/128", "scope6": "host"}],
                "hwaddr": ".",
                "up": True,
            },
            "eth0": {
                "ipv4": [],
                "ipv6": [],
                "hwaddr": "00:16:3e:de:51:a6",
                "up": False,
            },
        }
        assert (
            readResource("netinfo/netdev-formatted-output-down")
            == netdev_pformat()
        )

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_route_nettools_pformat(self, m_subp, m_which):
        """route_pformat properly rendering nettools route info."""

        def subp_netstat_route_selector(*args, **kwargs):
            if args[0] == ["netstat", "--route", "--numeric", "--extend"]:
                return (SAMPLE_ROUTE_OUT_V4, "")
            if args[0] == ["netstat", "-A", "inet6", "--route", "--numeric"]:
                return (SAMPLE_ROUTE_OUT_V6, "")
            raise Exception("Unexpected subp call %s" % args[0])

        m_subp.side_effect = subp_netstat_route_selector
        m_which.side_effect = lambda x: x if x == "netstat" else None
        content = route_pformat()
        assert ROUTE_FORMATTED_OUT == content

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_route_iproute_pformat(self, m_subp, m_which):
        """route_pformat properly rendering ip route info."""

        def subp_iproute_selector(*args, **kwargs):
            if ["ip", "-o", "route", "list"] == args[0]:
                return (SAMPLE_IPROUTE_OUT_V4, "")
            v6cmd = ["ip", "--oneline", "-6", "route", "list", "table", "all"]
            if v6cmd == args[0]:
                return (SAMPLE_IPROUTE_OUT_V6, "")
            raise Exception("Unexpected subp call %s" % args[0])

        m_subp.side_effect = subp_iproute_selector
        m_which.side_effect = lambda x: x if x == "ip" else None
        content = route_pformat()
        assert ROUTE_FORMATTED_OUT == content

    @mock.patch("cloudinit.netinfo.subp.which")
    @mock.patch("cloudinit.netinfo.subp.subp")
    def test_route_warn_on_missing_commands(self, m_subp, m_which, caplog):
        """route_pformat warns when missing both ip and 'netstat'."""
        m_which.return_value = None  # Niether ip nor netstat found
        content = route_pformat()
        assert "\n" == content
        log = caplog.records[0]
        assert log.levelname == "WARNING"
        assert log.msg == (
            "Could not print routes: missing 'ip' and 'netstat' commands"
        )
        m_subp.assert_not_called()

    @pytest.mark.parametrize(
        "input,expected",
        [
            # Test hwaddr set when link_type is ether,
            # Test up True when flags contains UP and LOWER_UP
            (
                [
                    {
                        "ifname": "eth0",
                        "link_type": "ether",
                        "address": "00:00:00:00:00:00",
                        "flags": ["LOOPBACK", "UP", "LOWER_UP"],
                    }
                ],
                {
                    "eth0": {
                        "hwaddr": "00:00:00:00:00:00",
                        "ipv4": [],
                        "ipv6": [],
                        "up": True,
                    }
                },
            ),
            # Test hwaddr not set when link_type is not ether
            # Test up False when flags does not contain both UP and LOWER_UP
            (
                [
                    {
                        "ifname": "eth0",
                        "link_type": "none",
                        "address": "00:00:00:00:00:00",
                        "flags": ["LOOPBACK", "UP"],
                    }
                ],
                {
                    "eth0": {
                        "hwaddr": "",
                        "ipv4": [],
                        "ipv6": [],
                        "up": False,
                    }
                },
            ),
            (
                [
                    {
                        "ifname": "eth0",
                        "addr_info": [
                            # Test for ipv4:
                            #  ip set correctly
                            #  mask set correctly
                            #  bcast set correctly
                            #  scope set correctly
                            {
                                "family": "inet",
                                "local": "10.0.0.1",
                                "broadcast": "10.0.0.255",
                                "prefixlen": 24,
                                "scope": "global",
                            },
                            # Test for ipv6:
                            #  ip set correctly
                            #  mask set correctly when no 'address' present
                            #  scope6 set correctly
                            {
                                "family": "inet6",
                                "local": "fd12:3456:7890:1234::5678:9012",
                                "prefixlen": 64,
                                "scope": "global",
                            },
                            # Test for ipv6:
                            #  mask not set when 'address' present
                            {
                                "family": "inet6",
                                "local": "fd12:3456:7890:1234::5678:9012",
                                "address": "fd12:3456:7890:1234::1",
                                "prefixlen": 64,
                            },
                        ],
                    }
                ],
                {
                    "eth0": {
                        "hwaddr": "",
                        "ipv4": [
                            {
                                "ip": "10.0.0.1",
                                "mask": "255.255.255.0",
                                "bcast": "10.0.0.255",
                                "scope": "global",
                            }
                        ],
                        "ipv6": [
                            {
                                "ip": "fd12:3456:7890:1234::5678:9012/64",
                                "scope6": "global",
                            },
                            {
                                "ip": "fd12:3456:7890:1234::5678:9012",
                                "scope6": "",
                            },
                        ],
                        "up": False,
                    }
                },
            ),
        ],
    )
    def test_netdev_info_iproute_json(self, input, expected):
        out = _netdev_info_iproute_json(json.dumps(input))
        assert out == expected


# vi: ts=4 expandtab
