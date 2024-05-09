# This file is part of cloud-init. See LICENSE file for license information.

import os
import signal
import socket
import subprocess
from textwrap import dedent

import pytest
import responses

from cloudinit.distros import alpine, amazon, centos, debian, freebsd, rhel
from cloudinit.distros.ubuntu import Distro
from cloudinit.net.dhcp import (
    DHCLIENT_FALLBACK_LEASE_DIR,
    Dhcpcd,
    InvalidDHCPLeaseFileError,
    IscDhclient,
    NoDHCPLeaseError,
    NoDHCPLeaseInterfaceError,
    NoDHCPLeaseMissingDhclientError,
    Udhcpc,
    maybe_perform_dhcp_discovery,
    networkd_load_leases,
)
from cloudinit.net.ephemeral import EphemeralDHCPv4
from cloudinit.subp import SubpResult
from cloudinit.util import ensure_file, load_binary_file, subp, write_file
from tests.unittests.helpers import (
    CiTestCase,
    ResponsesTestCase,
    example_netdev,
    mock,
    populate_dir,
)
from tests.unittests.util import MockDistro

PID_F = "/run/dhclient.pid"
LEASE_F = "/run/dhclient.lease"
DHCLIENT = "/sbin/dhclient"
ib_address_prefix = "00:00:00:00:00:00:00:00:00:00:00:00"


@pytest.mark.parametrize(
    "server_address,lease_file_content",
    (
        pytest.param(None, None, id="no_server_addr_on_absent_lease_file"),
        pytest.param(None, "", id="no_server_addr_on_empty_lease_file"),
        pytest.param(
            None,
            "lease {\n  fixed-address: 10.1.2.3;\n}\n",
            id="no_server_addr_when_no_server_ident",
        ),
        pytest.param(
            "10.4.5.6",
            "lease {\n fixed-address: 10.1.2.3;\n"
            "  option dhcp-server-identifier 10.4.5.6;\n"
            "  option dhcp-renewal-time 1800;\n}\n",
            id="server_addr_found_when_server_ident_present",
        ),
    ),
)
class TestParseDHCPServerFromLeaseFile:
    @pytest.mark.usefixtures("dhclient_exists")
    def test_find_server_address_when_present(
        self, server_address, lease_file_content, tmp_path
    ):
        """Test that we return None in the case of no file or file contains no
        server address, otherwise return the address.
        """
        dhclient = IscDhclient()
        dhclient.lease_file = tmp_path / "dhcp.leases"
        if lease_file_content:
            dhclient.lease_file.write_text(lease_file_content)
            if server_address:
                assert server_address == dhclient.get_newest_lease("eth0").get(
                    "dhcp-server-identifier"
                )
        else:
            assert None is dhclient.get_newest_lease("eth0").get(
                "dhcp-server-identifier"
            )


@pytest.mark.usefixtures("dhclient_exists")
class TestParseDHCPLeasesFile(CiTestCase):
    def test_parse_empty_lease_file_errors(self):
        """get_newest_lease errors when file content is empty."""
        client = IscDhclient()
        client.lease_file = self.tmp_path("leases")
        ensure_file(client.lease_file)
        assert not client.get_newest_lease("eth0")

    def test_parse_malformed_lease_file_content_errors(self):
        """IscDhclient.get_newest_lease errors when file content isn't
        dhcp leases.
        """
        client = IscDhclient()
        client.lease_file = self.tmp_path("leases")
        write_file(client.lease_file, "hi mom.")
        assert not client.get_newest_lease("eth0")

    def test_parse_multiple_leases(self):
        """IscDhclient().get_newest_lease returns the latest lease
        within.
        """
        client = IscDhclient()
        client.lease_file = self.tmp_path("leases")
        content = dedent(
            """
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              filename "http://192.168.2.50/boot.php?mac=${netX}";
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
              renew 4 2017/07/27 18:02:30;
              expire 5 2017/07/28 07:08:15;
            }
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              filename "http://192.168.2.50/boot.php?mac=${netX}";
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """
        )
        expected = {
            "interface": "wlp3s0",
            "fixed-address": "192.168.2.74",
            "filename": "http://192.168.2.50/boot.php?mac=${netX}",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
        }
        write_file(client.lease_file, content)
        got = client.get_newest_lease("eth0")
        self.assertCountEqual(got, expected)


@pytest.mark.usefixtures("dhclient_exists")
@pytest.mark.usefixtures("disable_netdev_info")
class TestDHCPRFC3442(CiTestCase):
    def test_parse_lease_finds_rfc3442_classless_static_routes(self):
        """IscDhclient().get_newest_lease() returns
        rfc3442-classless-static-routes.
        """
        client = IscDhclient()
        client.lease_file = self.tmp_path("leases")
        write_file(
            client.lease_file,
            dedent(
                """
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
              option rfc3442-classless-static-routes 0,130,56,240,1;
              renew 4 2017/07/27 18:02:30;
              expire 5 2017/07/28 07:08:15;
            }
            """
            ),
        )
        expected = {
            "interface": "wlp3s0",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "rfc3442-classless-static-routes": "0,130,56,240,1",
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        self.assertCountEqual(expected, client.get_newest_lease("eth0"))

    def test_parse_lease_finds_classless_static_routes(self):
        """
        IscDhclient().get_newest_lease returns classless-static-routes
        for Centos lease format.
        """
        client = IscDhclient()
        client.lease_file = self.tmp_path("leases")
        content = dedent(
            """
            lease {
              interface "wlp3s0";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
              option classless-static-routes 0 130.56.240.1;
              renew 4 2017/07/27 18:02:30;
              expire 5 2017/07/28 07:08:15;
            }
        """
        )
        expected = {
            "interface": "wlp3s0",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "classless-static-routes": "0 130.56.240.1",
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        write_file(client.lease_file, content)
        self.assertCountEqual(expected, client.get_newest_lease("eth0"))

    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_obtain_lease_parses_static_routes(self, m_maybe, m_ipv4):
        """EphemeralDHPCv4 parses rfc3442 routes for EphemeralIPv4Network"""
        m_maybe.return_value = {
            "interface": "wlp3s0",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "rfc3442-classless-static-routes": "0,130,56,240,1",
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        distro = MockDistro()
        eph = EphemeralDHCPv4(distro)
        eph.obtain_lease()
        expected_kwargs = {
            "interface": "wlp3s0",
            "interface_addrs_before_dhcp": example_netdev,
            "ip": "192.168.2.74",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
            "static_routes": [("0.0.0.0/0", "130.56.240.1")],
            "router": "192.168.2.1",
        }
        m_ipv4.assert_called_with(distro, **expected_kwargs)

    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_obtain_centos_lease_parses_static_routes(self, m_maybe, m_ipv4):
        """
        EphemeralDHPCv4 parses rfc3442 routes for EphemeralIPv4Network
        for Centos Lease format
        """
        m_maybe.return_value = {
            "interface": "wlp3s0",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "classless-static-routes": "0 130.56.240.1",
            "renew": "4 2017/07/27 18:02:30",
            "expire": "5 2017/07/28 07:08:15",
        }
        distro = MockDistro()
        eph = EphemeralDHCPv4(distro)
        eph.obtain_lease()
        expected_kwargs = {
            "interface": "wlp3s0",
            "interface_addrs_before_dhcp": example_netdev,
            "ip": "192.168.2.74",
            "prefix_or_mask": "255.255.255.0",
            "broadcast": "192.168.2.255",
            "static_routes": [("0.0.0.0/0", "130.56.240.1")],
            "router": "192.168.2.1",
        }
        m_ipv4.assert_called_with(distro, **expected_kwargs)


class TestDHCPParseStaticRoutes(CiTestCase):
    with_logs = True

    def test_parse_static_routes_empty_string(self):
        self.assertEqual([], IscDhclient.parse_static_routes(""))

    def test_parse_static_routes_invalid_input_returns_empty_list(self):
        rfc3442 = "32,169,254,169,254,130,56,248"
        self.assertEqual([], IscDhclient.parse_static_routes(rfc3442))

    def test_parse_static_routes_bogus_width_returns_empty_list(self):
        rfc3442 = "33,169,254,169,254,130,56,248"
        self.assertEqual([], IscDhclient.parse_static_routes(rfc3442))

    def test_parse_static_routes_single_ip(self):
        rfc3442 = "32,169,254,169,254,130,56,248,255"
        self.assertEqual(
            [("169.254.169.254/32", "130.56.248.255")],
            IscDhclient.parse_static_routes(rfc3442),
        )

    def test_parse_static_routes_single_ip_handles_trailing_semicolon(self):
        rfc3442 = "32,169,254,169,254,130,56,248,255;"
        self.assertEqual(
            [("169.254.169.254/32", "130.56.248.255")],
            IscDhclient.parse_static_routes(rfc3442),
        )

    def test_unknown_121(self):
        for unknown121 in [
            "0:a:0:0:1:20:a8:3f:81:10:a:0:0:1:20:a9:fe:a9:fe:a:0:0:1",
            "0:a:0:0:1:20:a8:3f:81:10:a:0:0:1:20:a9:fe:a9:fe:a:0:0:1;",
        ]:
            assert IscDhclient.parse_static_routes(unknown121) == [
                ("0.0.0.0/0", "10.0.0.1"),
                ("168.63.129.16/32", "10.0.0.1"),
                ("169.254.169.254/32", "10.0.0.1"),
            ]

    def test_parse_static_routes_default_route(self):
        rfc3442 = "0,130,56,240,1"
        self.assertEqual(
            [("0.0.0.0/0", "130.56.240.1")],
            IscDhclient.parse_static_routes(rfc3442),
        )

    def test_unspecified_gateway(self):
        rfc3442 = "32,169,254,169,254,0,0,0,0"
        self.assertEqual(
            [("169.254.169.254/32", "0.0.0.0")],
            IscDhclient.parse_static_routes(rfc3442),
        )

    def test_parse_static_routes_class_c_b_a(self):
        class_c = "24,192,168,74,192,168,0,4"
        class_b = "16,172,16,172,16,0,4"
        class_a = "8,10,10,0,0,4"
        rfc3442 = ",".join([class_c, class_b, class_a])
        self.assertEqual(
            sorted(
                [
                    ("192.168.74.0/24", "192.168.0.4"),
                    ("172.16.0.0/16", "172.16.0.4"),
                    ("10.0.0.0/8", "10.0.0.4"),
                ]
            ),
            sorted(IscDhclient.parse_static_routes(rfc3442)),
        )

    def test_parse_static_routes_logs_error_truncated(self):
        bad_rfc3442 = {
            "class_c": "24,169,254,169,10",
            "class_b": "16,172,16,10",
            "class_a": "8,10,10",
            "gateway": "0,0",
            "netlen": "33,0",
        }
        for rfc3442 in bad_rfc3442.values():
            self.assertEqual([], IscDhclient.parse_static_routes(rfc3442))

        logs = self.logs.getvalue()
        self.assertEqual(len(bad_rfc3442.keys()), len(logs.splitlines()))

    def test_parse_static_routes_returns_valid_routes_until_parse_err(self):
        class_c = "24,192,168,74,192,168,0,4"
        class_b = "16,172,16,172,16,0,4"
        class_a_error = "8,10,10,0,0"
        rfc3442 = ",".join([class_c, class_b, class_a_error])
        self.assertEqual(
            sorted(
                [
                    ("192.168.74.0/24", "192.168.0.4"),
                    ("172.16.0.0/16", "172.16.0.4"),
                ]
            ),
            sorted(IscDhclient.parse_static_routes(rfc3442)),
        )

        logs = self.logs.getvalue()
        self.assertIn(rfc3442, logs.splitlines()[0])

    def test_redhat_format(self):
        redhat_format = "24.191.168.128 192.168.128.1,0 192.168.128.1"
        self.assertEqual(
            sorted(
                [
                    ("191.168.128.0/24", "192.168.128.1"),
                    ("0.0.0.0/0", "192.168.128.1"),
                ]
            ),
            sorted(IscDhclient.parse_static_routes(redhat_format)),
        )

    def test_redhat_format_with_a_space_too_much_after_comma(self):
        redhat_format = "24.191.168.128 192.168.128.1, 0 192.168.128.1"
        self.assertEqual(
            sorted(
                [
                    ("191.168.128.0/24", "192.168.128.1"),
                    ("0.0.0.0/0", "192.168.128.1"),
                ]
            ),
            sorted(IscDhclient.parse_static_routes(redhat_format)),
        )


class TestDHCPDiscoveryClean:
    @mock.patch("cloudinit.distros.net.find_fallback_nic", return_value="eth9")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which")
    def test_dhcpcd_exits_with_error(
        self, m_which, m_subp, m_remove, m_fallback, caplog
    ):
        """Log and do nothing when nic is absent and no fallback is found."""
        m_subp.side_effect = [
            ("", ""),
            subp.ProcessExecutionError(exit_code=-5),
        ]

        with pytest.raises(NoDHCPLeaseError):
            maybe_perform_dhcp_discovery(Distro("fake but not", {}, None))

        assert "DHCP client selected: dhcpcd" in caplog.text

    @mock.patch("cloudinit.distros.net.find_fallback_nic", return_value="eth9")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which")
    def test_dhcp_client_failover(
        self, m_which, m_subp, m_remove, m_fallback, caplog
    ):
        """Log and do nothing when nic is absent and no fallback client is
        found."""
        m_subp.side_effect = [
            ("", ""),
            subp.ProcessExecutionError(exit_code=-5),
        ]

        m_which.side_effect = [False, False, False, False]
        with pytest.raises(NoDHCPLeaseError):
            maybe_perform_dhcp_discovery(Distro("somename", {}, None))

        assert "DHCP client not found: dhclient" in caplog.text
        assert "DHCP client not found: dhcpcd" in caplog.text
        assert "DHCP client not found: udhcpc" in caplog.text

    @mock.patch("cloudinit.net.dhcp.subp.which")
    @mock.patch("cloudinit.distros.net.find_fallback_nic")
    def test_absent_dhclient_command(self, m_fallback, m_which, caplog):
        """When dhclient doesn't exist in the OS, log the issue and no-op."""
        m_fallback.return_value = "eth9"
        m_which.return_value = None  # dhclient isn't found
        with pytest.raises(NoDHCPLeaseMissingDhclientError):
            maybe_perform_dhcp_discovery(Distro("whoa", {}, None))

        assert "DHCP client not found: dhclient" in caplog.text
        assert "DHCP client not found: dhcpcd" in caplog.text
        assert "DHCP client not found: udhcpc" in caplog.text

    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("time.sleep", mock.MagicMock())
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.net.dhcp.util.wait_for_files", return_value=False)
    def test_dhcp_discovery_warns_invalid_pid(
        self, m_wait, m_which, m_subp, m_kill, m_remove, caplog
    ):
        """dhcp_discovery logs a warning when pidfile contains invalid content.

        Lease processing still occurs and no proc kill is attempted.
        """
        m_subp.return_value = ("", "")

        lease_content = dedent(
            """
            lease {
              interface "eth9";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """
        )

        with mock.patch(
            "cloudinit.util.load_text_file", return_value=lease_content
        ):
            assert {
                "interface": "eth9",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
            } == IscDhclient().get_newest_lease("eth0")
        with pytest.raises(InvalidDHCPLeaseFileError):
            with mock.patch("cloudinit.util.load_text_file", return_value=""):
                IscDhclient().dhcp_discovery("eth9", distro=MockDistro())
        assert (
            "dhclient(pid=, parentpid=unknown) failed to daemonize after"
            " 10.0 seconds" in caplog.text
        )
        m_kill.assert_not_called()

    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.util.wait_for_files")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    def test_dhcp_discovery_waits_on_lease_and_pid(
        self, m_subp, m_which, m_wait, m_kill, m_remove, caplog
    ):
        """dhcp_discovery waits for the presence of pidfile and dhcp.leases."""
        m_subp.return_value = ("", "")

        # Don't create pid or leases file
        m_wait.return_value = [PID_F]  # Return the missing pidfile wait for
        assert {} == IscDhclient().dhcp_discovery("eth9", distro=MockDistro())
        m_wait.assert_called_once_with(
            [PID_F, LEASE_F], maxwait=5, naplen=0.01
        )
        assert (
            "dhclient did not produce expected files: dhclient.pid"
            in caplog.text
        )
        m_kill.assert_not_called()

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=False)
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.util.wait_for_files", return_value=False)
    def test_dhcp_discovery(
        self,
        m_wait,
        m_which,
        m_subp,
        m_kill,
        m_remove,
        mocked_is_ib_interface,
    ):
        """dhcp_discovery brings up the interface and runs dhclient.

        It also returns the parsed dhcp.leases file.
        """
        m_subp.return_value = ("", "")
        lease_content = dedent(
            """
            lease {
              interface "eth9";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """
        )
        my_pid = 1
        with mock.patch(
            "cloudinit.util.load_text_file", side_effect=["1", lease_content]
        ):
            assert {
                "interface": "eth9",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
            } == IscDhclient().dhcp_discovery("eth9", distro=MockDistro())
        # Interface was brought up before dhclient called
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "eth9", "up"],
                ),
                mock.call(
                    [
                        DHCLIENT,
                        "-1",
                        "-v",
                        "-lf",
                        LEASE_F,
                        "-pf",
                        PID_F,
                        "-sf",
                        "/bin/true",
                        "eth9",
                    ],
                ),
            ]
        )
        m_kill.assert_has_calls([mock.call(my_pid, signal.SIGKILL)])
        mocked_is_ib_interface.assert_called_once_with("eth9")

    @mock.patch("cloudinit.temp_utils.get_tmp_ancestor", return_value="/tmp")
    @mock.patch("cloudinit.util.write_file")
    @mock.patch(
        "cloudinit.net.dhcp.get_interface_mac",
        return_value="%s:AA:AA:AA:00:00:AA:AA:AA" % ib_address_prefix,
    )
    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=True)
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.net.dhcp.subp.subp", return_value=("", ""))
    @mock.patch("cloudinit.util.wait_for_files", return_value=False)
    def test_dhcp_discovery_ib(
        self,
        m_wait,
        m_subp,
        m_which,
        m_kill,
        m_remove,
        mocked_is_ib_interface,
        get_interface_mac,
        mocked_write_file,
        mocked_get_tmp_ancestor,
    ):
        """dhcp_discovery brings up the interface and runs dhclient.

        It also returns the parsed dhcp.leases file.
        """
        lease_content = dedent(
            """
            lease {
              interface "ib0";
              fixed-address 192.168.2.74;
              option subnet-mask 255.255.255.0;
              option routers 192.168.2.1;
            }
        """
        )
        my_pid = 1
        with mock.patch(
            "cloudinit.util.load_text_file", side_effect=["1", lease_content]
        ):
            assert {
                "interface": "ib0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
            } == IscDhclient().dhcp_discovery("ib0", distro=MockDistro())
        # Interface was brought up before dhclient called
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "ib0", "up"],
                ),
                mock.call(
                    [
                        DHCLIENT,
                        "-1",
                        "-v",
                        "-lf",
                        LEASE_F,
                        "-pf",
                        PID_F,
                        "-sf",
                        "/bin/true",
                        "-cf",
                        "/tmp/ib0-dhclient.conf",
                        "ib0",
                    ],
                ),
            ]
        )
        m_kill.assert_has_calls([mock.call(my_pid, signal.SIGKILL)])
        mocked_is_ib_interface.assert_called_once_with("ib0")
        get_interface_mac.assert_called_once_with("ib0")
        mocked_get_tmp_ancestor.assert_called_once_with(needs_exe=True)
        mocked_write_file.assert_called_once_with(
            "/tmp/ib0-dhclient.conf",
            'interface "ib0" {send dhcp-client-identifier '
            "20:AA:AA:AA:00:00:AA:AA:AA;}",
        )

    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.util.wait_for_files")
    def test_dhcp_output_error_stream(
        self, m_wait, m_which, m_subp, m_kill, m_remove, tmpdir
    ):
        """dhcp_log_func is called with the output and error streams of
        dhclient when the callable is passed."""
        dhclient_err = "FAKE DHCLIENT ERROR"
        dhclient_out = "FAKE DHCLIENT OUT"
        m_subp.return_value = (dhclient_out, dhclient_err)
        lease_content = dedent(
            """
                lease {
                  interface "eth9";
                  fixed-address 192.168.2.74;
                  option subnet-mask 255.255.255.0;
                  option routers 192.168.2.1;
                }
            """
        )
        lease_file = os.path.join(tmpdir, "dhcp.leases")
        write_file(lease_file, lease_content)
        pid_file = os.path.join(tmpdir, "dhclient.pid")
        my_pid = 1
        write_file(pid_file, "%d\n" % my_pid)

        def dhcp_log_func(out, err):
            assert out == dhclient_out
            assert err == dhclient_err

        IscDhclient().dhcp_discovery(
            "eth9", dhcp_log_func=dhcp_log_func, distro=MockDistro()
        )


class TestSystemdParseLeases(CiTestCase):
    lxd_lease = dedent(
        """\
    # This is private data. Do not parse.
    ADDRESS=10.75.205.242
    NETMASK=255.255.255.0
    ROUTER=10.75.205.1
    SERVER_ADDRESS=10.75.205.1
    NEXT_SERVER=10.75.205.1
    BROADCAST=10.75.205.255
    T1=1580
    T2=2930
    LIFETIME=3600
    DNS=10.75.205.1
    DOMAINNAME=lxd
    HOSTNAME=a1
    CLIENTID=ffe617693400020000ab110c65a6a0866931c2
    """
    )

    lxd_parsed = {
        "ADDRESS": "10.75.205.242",
        "NETMASK": "255.255.255.0",
        "ROUTER": "10.75.205.1",
        "SERVER_ADDRESS": "10.75.205.1",
        "NEXT_SERVER": "10.75.205.1",
        "BROADCAST": "10.75.205.255",
        "T1": "1580",
        "T2": "2930",
        "LIFETIME": "3600",
        "DNS": "10.75.205.1",
        "DOMAINNAME": "lxd",
        "HOSTNAME": "a1",
        "CLIENTID": "ffe617693400020000ab110c65a6a0866931c2",
    }

    azure_lease = dedent(
        """\
    # This is private data. Do not parse.
    ADDRESS=10.132.0.5
    NETMASK=255.255.255.255
    ROUTER=10.132.0.1
    SERVER_ADDRESS=169.254.169.254
    NEXT_SERVER=10.132.0.1
    MTU=1460
    T1=43200
    T2=75600
    LIFETIME=86400
    DNS=169.254.169.254
    NTP=169.254.169.254
    DOMAINNAME=c.ubuntu-foundations.internal
    DOMAIN_SEARCH_LIST=c.ubuntu-foundations.internal google.internal
    HOSTNAME=tribaal-test-171002-1349.c.ubuntu-foundations.internal
    ROUTES=10.132.0.1/32,0.0.0.0 0.0.0.0/0,10.132.0.1
    CLIENTID=ff405663a200020000ab11332859494d7a8b4c
    OPTION_245=624c3620
    """
    )

    azure_parsed = {
        "ADDRESS": "10.132.0.5",
        "NETMASK": "255.255.255.255",
        "ROUTER": "10.132.0.1",
        "SERVER_ADDRESS": "169.254.169.254",
        "NEXT_SERVER": "10.132.0.1",
        "MTU": "1460",
        "T1": "43200",
        "T2": "75600",
        "LIFETIME": "86400",
        "DNS": "169.254.169.254",
        "NTP": "169.254.169.254",
        "DOMAINNAME": "c.ubuntu-foundations.internal",
        "DOMAIN_SEARCH_LIST": "c.ubuntu-foundations.internal google.internal",
        "HOSTNAME": "tribaal-test-171002-1349.c.ubuntu-foundations.internal",
        "ROUTES": "10.132.0.1/32,0.0.0.0 0.0.0.0/0,10.132.0.1",
        "CLIENTID": "ff405663a200020000ab11332859494d7a8b4c",
        "OPTION_245": "624c3620",
    }

    def setUp(self):
        super(TestSystemdParseLeases, self).setUp()
        self.lease_d = self.tmp_dir()

    def test_no_leases_returns_empty_dict(self):
        """A leases dir with no lease files should return empty dictionary."""
        self.assertEqual({}, networkd_load_leases(self.lease_d))

    def test_no_leases_dir_returns_empty_dict(self):
        """A non-existing leases dir should return empty dict."""
        enodir = os.path.join(self.lease_d, "does-not-exist")
        self.assertEqual({}, networkd_load_leases(enodir))

    def test_single_leases_file(self):
        """A leases dir with one leases file."""
        populate_dir(self.lease_d, {"2": self.lxd_lease})
        self.assertEqual(
            {"2": self.lxd_parsed}, networkd_load_leases(self.lease_d)
        )

    def test_single_azure_leases_file(self):
        """On Azure, option 245 should be present, verify it specifically."""
        populate_dir(self.lease_d, {"1": self.azure_lease})
        self.assertEqual(
            {"1": self.azure_parsed}, networkd_load_leases(self.lease_d)
        )

    def test_multiple_files(self):
        """Multiple leases files on azure with one found return that value."""
        self.maxDiff = None
        populate_dir(
            self.lease_d, {"1": self.azure_lease, "9": self.lxd_lease}
        )
        self.assertEqual(
            {"1": self.azure_parsed, "9": self.lxd_parsed},
            networkd_load_leases(self.lease_d),
        )


@pytest.mark.usefixtures("disable_netdev_info")
class TestEphemeralDhcpNoNetworkSetup(ResponsesTestCase):
    @mock.patch("cloudinit.net.dhcp.maybe_perform_dhcp_discovery")
    def test_ephemeral_dhcp_no_network_if_url_connectivity(self, m_dhcp):
        """No EphemeralDhcp4 network setup when connectivity_url succeeds."""
        url = "http://example.org/index.html"

        self.responses.add(responses.GET, url)
        with EphemeralDHCPv4(
            MockDistro(),
            connectivity_url_data={"url": url},
        ) as lease:
            self.assertIsNone(lease)
        # Ensure that no teardown happens:
        m_dhcp.assert_not_called()

    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_ephemeral_dhcp_setup_network_if_url_connectivity(
        self, m_dhcp, m_subp
    ):
        """No EphemeralDhcp4 network setup when connectivity_url succeeds."""
        url = "http://example.org/index.html"
        m_dhcp.return_value = {
            "interface": "eth9",
            "fixed-address": "192.168.2.2",
            "subnet-mask": "255.255.0.0",
        }
        m_subp.return_value = ("", "")

        self.responses.add(responses.GET, url, body=b"", status=404)
        with EphemeralDHCPv4(
            MockDistro(),
            connectivity_url_data={"url": url},
        ) as lease:
            self.assertEqual(m_dhcp.return_value, lease)
        # Ensure that dhcp discovery occurs
        m_dhcp.assert_called_once()


@pytest.mark.parametrize(
    "error_class",
    [
        NoDHCPLeaseInterfaceError,
        NoDHCPLeaseInterfaceError,
        NoDHCPLeaseMissingDhclientError,
    ],
)
@pytest.mark.usefixtures("disable_netdev_info")
class TestEphemeralDhcpLeaseErrors:
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_obtain_lease_raises_error(self, m_dhcp, error_class):
        m_dhcp.side_effect = [error_class()]

        with pytest.raises(error_class):
            EphemeralDHCPv4(
                MockDistro(),
            ).obtain_lease()

        assert len(m_dhcp.mock_calls) == 1

    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_obtain_lease_umbrella_error(self, m_dhcp, error_class):
        m_dhcp.side_effect = [error_class()]
        with pytest.raises(NoDHCPLeaseError):
            EphemeralDHCPv4(
                MockDistro(),
            ).obtain_lease()

        assert len(m_dhcp.mock_calls) == 1

    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_ctx_mgr_raises_error(self, m_dhcp, error_class):
        m_dhcp.side_effect = [error_class()]

        with pytest.raises(error_class):
            with EphemeralDHCPv4(
                MockDistro(),
            ):
                pass

        assert len(m_dhcp.mock_calls) == 1

    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_ctx_mgr_umbrella_error(self, m_dhcp, error_class):
        m_dhcp.side_effect = [error_class()]
        with pytest.raises(NoDHCPLeaseError):
            with EphemeralDHCPv4(
                MockDistro(),
            ):
                pass

        assert len(m_dhcp.mock_calls) == 1


class TestUDHCPCDiscoveryClean(CiTestCase):
    with_logs = True
    maxDiff = None

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=False)
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/udhcpc")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_text_file")
    @mock.patch("cloudinit.util.write_file")
    def test_udhcpc_discovery(
        self,
        m_write_file,
        m_load_file,
        m_loadjson,
        m_subp,
        m_remove,
        m_which,
        mocked_is_ib_interface,
    ):
        """dhcp_discovery runs udcpc and parse the dhcp leases."""
        m_subp.return_value = ("", "")
        m_loadjson.return_value = {
            "interface": "eth9",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "static_routes": "10.240.0.1/32 0.0.0.0 0.0.0.0/0 10.240.0.1",
        }
        self.assertEqual(
            {
                "fixed-address": "192.168.2.74",
                "interface": "eth9",
                "routers": "192.168.2.1",
                "static_routes": "10.240.0.1/32 0.0.0.0 0.0.0.0/0 10.240.0.1",
                "subnet-mask": "255.255.255.0",
            },
            Udhcpc().dhcp_discovery("eth9", distro=MockDistro()),
        )
        # Interface was brought up before dhclient called
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "eth9", "up"],
                ),
                mock.call(
                    [
                        "/sbin/udhcpc",
                        "-O",
                        "staticroutes",
                        "-i",
                        "eth9",
                        "-s",
                        "/var/tmp/cloud-init/udhcpc_script",
                        "-n",
                        "-q",
                        "-f",
                        "-v",
                    ],
                    update_env={
                        "LEASE_FILE": "/var/tmp/cloud-init/eth9.lease.json"
                    },
                    capture=True,
                ),
            ]
        )

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=True)
    @mock.patch(
        "cloudinit.net.dhcp.get_interface_mac",
        return_value="%s:AA:AA:AA:00:00:AA:AA:AA" % ib_address_prefix,
    )
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/udhcpc")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_text_file")
    @mock.patch("cloudinit.util.write_file")
    def test_udhcpc_discovery_ib(
        self,
        m_write_file,
        m_load_file,
        m_loadjson,
        m_subp,
        m_remove,
        m_which,
        m_get_ib_interface_hwaddr,
        m_is_ib_interface,
    ):
        """dhcp_discovery runs udcpc and parse the dhcp leases."""
        m_subp.return_value = ("", "")
        m_loadjson.return_value = {
            "interface": "ib0",
            "fixed-address": "192.168.2.74",
            "subnet-mask": "255.255.255.0",
            "routers": "192.168.2.1",
            "static_routes": "10.240.0.1/32 0.0.0.0 0.0.0.0/0 10.240.0.1",
        }
        self.assertEqual(
            {
                "fixed-address": "192.168.2.74",
                "interface": "ib0",
                "routers": "192.168.2.1",
                "static_routes": "10.240.0.1/32 0.0.0.0 0.0.0.0/0 10.240.0.1",
                "subnet-mask": "255.255.255.0",
            },
            Udhcpc().dhcp_discovery("ib0", distro=MockDistro()),
        )
        # Interface was brought up before dhclient called
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "ib0", "up"],
                ),
                mock.call(
                    [
                        "/sbin/udhcpc",
                        "-O",
                        "staticroutes",
                        "-i",
                        "ib0",
                        "-s",
                        "/var/tmp/cloud-init/udhcpc_script",
                        "-n",
                        "-q",
                        "-f",
                        "-v",
                        "-x",
                        "0x3d:20AAAAAA0000AAAAAA",
                    ],
                    update_env={
                        "LEASE_FILE": "/var/tmp/cloud-init/ib0.lease.json"
                    },
                    capture=True,
                ),
            ]
        )


class TestISCDHClient(CiTestCase):
    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            # rhel style lease file
            "dhclient-0-u-u-i-d-enp2s0f0.lease",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_rhel(self, *_):
        """
        Test that an rhel style lease has been found
        """
        self.assertEqual(
            "/var/lib/NetworkManager/dhclient-0-u-u-i-d-enp2s0f0.lease",
            IscDhclient.get_newest_lease_file_from_distro(rhel.Distro),
        )

    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            # amazon linux style
            "dhclient--eth0.leases",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_amazonlinux(self, *_):
        """
        Test that an amazon style lease has been found
        """
        self.assertEqual(
            "/var/lib/dhcp/dhclient--eth0.leases",
            IscDhclient.get_newest_lease_file_from_distro(amazon.Distro),
        )

    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            # freebsd style lease file
            "dhclient.leases.vtynet0",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_freebsd(self, *_):
        """
        Test that an freebsd style lease has been found
        """
        self.assertEqual(
            "/var/db/dhclient.leases.vtynet0",
            IscDhclient.get_newest_lease_file_from_distro(freebsd.Distro),
        )

    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            # alpine style lease file
            "dhclient.leases",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_alpine(self, *_):
        """
        Test that an alpine style lease has been found
        """
        self.assertEqual(
            "/var/lib/dhcp/dhclient.leases",
            IscDhclient.get_newest_lease_file_from_distro(alpine.Distro),
        )

    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            # debian style lease file
            "dhclient.eth0.leases",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_debian(self, *_):
        """
        Test that an debian style lease has been found
        """
        self.assertEqual(
            "/var/lib/dhcp/dhclient.eth0.leases",
            IscDhclient.get_newest_lease_file_from_distro(debian.Distro),
        )

    # If argument to listdir is '/var/lib/NetworkManager'
    # then mock an empty reply
    # otherwise mock a reply with leasefile
    @mock.patch(
        "os.listdir",
        side_effect=lambda x: (
            []
            if x == "/var/lib/NetworkManager"
            else ["some_file", "!@#$-eth0.lease", "some_other_file"]
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_fallback_when_nothing_found(self, *_):
        """
        This tests a situation where Distro provides lease information
        but the lease wasn't found on that location
        """
        self.assertEqual(
            os.path.join(DHCLIENT_FALLBACK_LEASE_DIR, "!@#$-eth0.lease"),
            IscDhclient.get_newest_lease_file_from_distro(
                rhel.Distro("", {}, {})
            ),
        )

    @mock.patch(
        "os.listdir",
        return_value=(
            "some_file",
            "totally_not_a_leasefile",
            "some_other_file",
        ),
    )
    @mock.patch("os.path.getmtime", return_value=123.45)
    def test_get_newest_lease_file_from_distro_notfound(self, *_):
        """
        Test the case when no leases were found
        """
        # Any Distro would suffice for the absense test, choose Centos then.
        self.assertEqual(
            None,
            IscDhclient.get_newest_lease_file_from_distro(centos.Distro),
        )


class TestDhcpcd:
    def test_parse_lease_dump(self):
        lease = dedent(
            """
            broadcast_address='192.168.15.255'
            dhcp_lease_time='3600'
            dhcp_message_type='5'
            dhcp_server_identifier='192.168.0.1'
            domain_name='us-east-2.compute.internal'
            domain_name_servers='192.168.0.2'
            host_name='ip-192-168-0-212'
            interface_mtu='9001'
            ip_address='192.168.0.212'
            network_number='192.168.0.0'
            routers='192.168.0.1'
            subnet_cidr='20'
            subnet_mask='255.255.240.0'
            """
        )
        with mock.patch("cloudinit.net.dhcp.util.load_binary_file"):
            parsed_lease = Dhcpcd.parse_dhcpcd_lease(lease, "eth0")
        assert "eth0" == parsed_lease["interface"]
        assert "192.168.15.255" == parsed_lease["broadcast-address"]
        assert "192.168.0.212" == parsed_lease["fixed-address"]
        assert "255.255.240.0" == parsed_lease["subnet-mask"]
        assert "192.168.0.1" == parsed_lease["routers"]

    @pytest.mark.parametrize(
        "lease, parsed",
        (
            pytest.param(
                """

                domain_name='us-east-2.compute.internal'

                domain_name_servers='192.168.0.2'

                """,
                {
                    "domain_name": "us-east-2.compute.internal",
                    "domain_name_servers": "192.168.0.2",
                },
                id="lease_has_empty_lines",
            ),
            pytest.param(
                """
                domain_name='us-east-2.compute.internal'
                not-a-kv-pair
                domain_name_servers='192.168.0.2'
                """,
                {
                    "domain_name": "us-east-2.compute.internal",
                    "domain_name_servers": "192.168.0.2",
                },
                id="lease_has_values_that_arent_key_value_pairs",
            ),
            pytest.param(
                """
                domain_name='us-east=2.compute.internal'
                """,
                {
                    "domain_name": "us-east=2.compute.internal",
                },
                id="lease_has_kv_pair_including_equals_sign_in_value",
            ),
        ),
    )
    def test_parse_lease_dump_resilience(self, lease, parsed):
        with mock.patch("cloudinit.net.dhcp.util.load_binary_file"):
            Dhcpcd.parse_dhcpcd_lease(dedent(lease), "eth0")

    def test_parse_lease_dump_fails(self):
        def _raise():
            raise ValueError()

        lease = mock.Mock()
        lease.strip = _raise

        with pytest.raises(InvalidDHCPLeaseFileError):
            with mock.patch("cloudinit.net.dhcp.util.load_binary_file"):
                Dhcpcd.parse_dhcpcd_lease(lease, "eth0")

        with pytest.raises(InvalidDHCPLeaseFileError):
            with mock.patch("cloudinit.net.dhcp.util.load_binary_file"):
                lease = dedent(
                    """
                    fail
                    """
                )
                Dhcpcd.parse_dhcpcd_lease(lease, "eth0")

    @pytest.mark.parametrize(
        "lease_file, option_245",
        (
            pytest.param("enp24s0.lease", None, id="no option 245"),
            pytest.param(
                "eth0.lease",
                socket.inet_aton("168.63.129.16"),
                id="a valid option 245",
            ),
        ),
    )
    def test_parse_raw_lease(self, lease_file, option_245):
        lease = load_binary_file(f"tests/data/net/dhcp/{lease_file}")
        assert option_245 == Dhcpcd.parse_unknown_options_from_packet(
            lease, 245
        )

    def test_parse_classless_static_routes(self):
        lease = dedent(
            """
            broadcast_address='10.0.0.255'
            classless_static_routes='0.0.0.0/0 10.0.0.1 168.63.129.16/32"""
            """ 10.0.0.1 169.254.169.254/32 10.0.0.1'
            dhcp_lease_time='4294967295'
            dhcp_message_type='5'
            dhcp_rebinding_time='4294967295'
            dhcp_renewal_time='4294967295'
            dhcp_server_identifier='168.63.129.16'
            domain_name='ilo2tr0xng2exgucxg20yx0tjb.gx.internal.cloudapp.net'
            domain_name_servers='168.63.129.16'
            ip_address='10.0.0.5'
            network_number='10.0.0.0'
            routers='10.0.0.1'
            server_name='DSM111070915004'
            subnet_cidr='24'
            subnet_mask='255.255.255.0'
            """
        )
        with mock.patch("cloudinit.net.dhcp.util.load_binary_file"):
            parsed_lease = Dhcpcd.parse_dhcpcd_lease(lease, "eth0")
        assert [
            ("0.0.0.0/0", "10.0.0.1"),
            ("168.63.129.16/32", "10.0.0.1"),
            ("169.254.169.254/32", "10.0.0.1"),
        ] == Dhcpcd.parse_static_routes(parsed_lease["static_routes"])

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=True)
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhcpcd")
    @mock.patch("cloudinit.net.dhcp.os.killpg")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_binary_file")
    @mock.patch("cloudinit.util.write_file")
    def test_dhcpcd_discovery_ib(
        self,
        m_write_file,
        m_load_file,
        m_loadjson,
        m_subp,
        m_remove,
        m_which,
        m_is_ib_interface,
    ):
        """dhcp_discovery runs udcpc and parse the dhcp leases."""
        m_subp.return_value = SubpResult("a=b", "")
        Dhcpcd().dhcp_discovery("ib0", distro=MockDistro())
        # Interface was brought up before dhclient called
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "ib0", "up"],
                ),
                mock.call(
                    [
                        "/sbin/dhcpcd",
                        "--ipv4only",
                        "--waitip",
                        "--persistent",
                        "--noarp",
                        "--script=/bin/true",
                        "--clientid",
                        "ib0",
                    ],
                    timeout=Dhcpcd.timeout,
                ),
            ]
        )

    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhcpcd")
    @mock.patch("cloudinit.net.dhcp.os.killpg")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_binary_file")
    @mock.patch("cloudinit.util.write_file")
    def test_dhcpcd_discovery_timeout(
        self,
        m_write_file,
        m_load_file,
        m_loadjson,
        m_subp,
        m_remove,
        m_which,
    ):
        """Verify dhcpcd timeout results in NoDHCPLeaseError exception."""
        m_subp.side_effect = [
            SubpResult("a=b", ""),
            subprocess.TimeoutExpired(
                "/sbin/dhcpcd", timeout=6, output="testout", stderr="testerr"
            ),
        ]
        with pytest.raises(NoDHCPLeaseError):
            Dhcpcd().dhcp_discovery("eth0", distro=MockDistro())

        m_subp.assert_has_calls(
            [
                mock.call(
                    ["ip", "link", "set", "dev", "eth0", "up"],
                ),
                mock.call(
                    [
                        "/sbin/dhcpcd",
                        "--ipv4only",
                        "--waitip",
                        "--persistent",
                        "--noarp",
                        "--script=/bin/true",
                        "eth0",
                    ],
                    timeout=Dhcpcd.timeout,
                ),
            ]
        )


class TestMaybePerformDhcpDiscovery:
    def test_none_and_missing_fallback(self):
        with pytest.raises(NoDHCPLeaseInterfaceError):
            distro = mock.Mock(fallback_interface=None)
            maybe_perform_dhcp_discovery(distro, None)
