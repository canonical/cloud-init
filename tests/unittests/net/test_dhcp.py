# This file is part of cloud-init. See LICENSE file for license information.

import os
import signal
from textwrap import dedent

import pytest
import responses

from cloudinit.net.dhcp import (
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
from cloudinit.util import ensure_file, subp, write_file
from tests.unittests.helpers import (
    CiTestCase,
    ResponsesTestCase,
    mock,
    populate_dir,
)
from tests.unittests.util import MockDistro

PID_F = "/run/dhclient.pid"
LEASE_F = "/run/dhclient.lease"
DHCLIENT = "/sbin/dhclient"


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
    def test_find_server_address_when_present(
        self, server_address, lease_file_content, tmp_path
    ):
        """Test that we return None in the case of no file or file contains no
        server address, otherwise return the address.
        """
        lease_file = tmp_path / "dhcp.leases"
        if server_address:
            if lease_file_content:
                lease_file.write_text(lease_file_content)
            assert (
                server_address
                == IscDhclient.parse_dhcp_server_from_lease_file(lease_file)
            )
        else:
            assert not IscDhclient.parse_dhcp_server_from_lease_file(
                lease_file
            )


class TestParseDHCPLeasesFile(CiTestCase):
    def test_parse_empty_lease_file_errors(self):
        """parse_dhcp_lease_file errors when file content is empty."""
        empty_file = self.tmp_path("leases")
        ensure_file(empty_file)
        with self.assertRaises(InvalidDHCPLeaseFileError) as context_manager:
            IscDhclient.parse_dhcp_lease_file(empty_file)
        error = context_manager.exception
        self.assertIn("Cannot parse empty dhcp lease file", str(error))

    def test_parse_malformed_lease_file_content_errors(self):
        """IscDhclient.parse_dhcp_lease_file errors when file content isn't
        dhcp leases.
        """
        non_lease_file = self.tmp_path("leases")
        write_file(non_lease_file, "hi mom.")
        with self.assertRaises(InvalidDHCPLeaseFileError) as context_manager:
            IscDhclient.parse_dhcp_lease_file(non_lease_file)
        error = context_manager.exception
        self.assertIn("Cannot parse dhcp lease file", str(error))

    def test_parse_multiple_leases(self):
        """IscDhclient.parse_dhcp_lease_file returns a list of all leases
        within.
        """
        lease_file = self.tmp_path("leases")
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
        expected = [
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
                "filename": "http://192.168.2.50/boot.php?mac=${netX}",
            },
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "filename": "http://192.168.2.50/boot.php?mac=${netX}",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
            },
        ]
        write_file(lease_file, content)
        self.assertCountEqual(
            expected, IscDhclient.parse_dhcp_lease_file(lease_file)
        )


class TestDHCPRFC3442(CiTestCase):
    def test_parse_lease_finds_rfc3442_classless_static_routes(self):
        """IscDhclient.parse_dhcp_lease_file returns
        rfc3442-classless-static-routes.
        """
        lease_file = self.tmp_path("leases")
        content = dedent(
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
        )
        expected = [
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
                "rfc3442-classless-static-routes": "0,130,56,240,1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
            }
        ]
        write_file(lease_file, content)
        self.assertCountEqual(
            expected, IscDhclient.parse_dhcp_lease_file(lease_file)
        )

    def test_parse_lease_finds_classless_static_routes(self):
        """
        IscDhclient.parse_dhcp_lease_file returns classless-static-routes
        for Centos lease format.
        """
        lease_file = self.tmp_path("leases")
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
        expected = [
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
                "classless-static-routes": "0 130.56.240.1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
            }
        ]
        write_file(lease_file, content)
        self.assertCountEqual(
            expected, IscDhclient.parse_dhcp_lease_file(lease_file)
        )

    @mock.patch("cloudinit.net.ephemeral.EphemeralIPv4Network")
    @mock.patch("cloudinit.net.ephemeral.maybe_perform_dhcp_discovery")
    def test_obtain_lease_parses_static_routes(self, m_maybe, m_ipv4):
        """EphemeralDHPCv4 parses rfc3442 routes for EphemeralIPv4Network"""
        lease = [
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
                "rfc3442-classless-static-routes": "0,130,56,240,1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
            }
        ]
        m_maybe.return_value = lease
        distro = MockDistro()
        eph = EphemeralDHCPv4(distro)
        eph.obtain_lease()
        expected_kwargs = {
            "interface": "wlp3s0",
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
        lease = [
            {
                "interface": "wlp3s0",
                "fixed-address": "192.168.2.74",
                "subnet-mask": "255.255.255.0",
                "routers": "192.168.2.1",
                "classless-static-routes": "0 130.56.240.1",
                "renew": "4 2017/07/27 18:02:30",
                "expire": "5 2017/07/28 07:08:15",
            }
        ]
        m_maybe.return_value = lease
        distro = MockDistro()
        eph = EphemeralDHCPv4(distro)
        eph.obtain_lease()
        expected_kwargs = {
            "interface": "wlp3s0",
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


class TestDHCPDiscoveryClean(CiTestCase):
    with_logs = True
    ib_address_prefix = "00:00:00:00:00:00:00:00:00:00:00:00"

    @mock.patch("cloudinit.net.dhcp.find_fallback_nic")
    def test_no_fallback_nic_found(self, m_fallback_nic):
        """Log and do nothing when nic is absent and no fallback is found."""
        m_fallback_nic.return_value = None  # No fallback nic found

        with pytest.raises(NoDHCPLeaseInterfaceError):
            maybe_perform_dhcp_discovery(MockDistro())

        self.assertIn(
            "Skip dhcp_discovery: Unable to find fallback nic.",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.find_fallback_nic", return_value="eth9")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which")
    def test_dhclient_exits_with_error(
        self, m_which, m_subp, m_remove, m_fallback
    ):
        """Log and do nothing when nic is absent and no fallback is found."""
        m_subp.side_effect = [
            ("", ""),
            subp.ProcessExecutionError(exit_code=-5),
        ]

        with pytest.raises(NoDHCPLeaseError):
            maybe_perform_dhcp_discovery(MockDistro())

        self.assertIn(
            "DHCP client selected: dhclient",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.find_fallback_nic", return_value="eth9")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which")
    def test_dhcp_client_failover(self, m_which, m_subp, m_remove, m_fallback):
        """Log and do nothing when nic is absent and no fallback is found."""
        m_subp.side_effect = [
            ("", ""),
            subp.ProcessExecutionError(exit_code=-5),
        ]

        m_which.side_effect = [False, True]
        with pytest.raises(NoDHCPLeaseError):
            maybe_perform_dhcp_discovery(MockDistro())

        self.assertIn(
            "DHCP client not found: dhclient",
            self.logs.getvalue(),
        )
        self.assertIn(
            "DHCP client not found: dhcpcd",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.find_fallback_nic", return_value=None)
    def test_provided_nic_does_not_exist(self, m_fallback_nic):
        """When the provided nic doesn't exist, log a message and no-op."""
        with pytest.raises(NoDHCPLeaseInterfaceError):
            maybe_perform_dhcp_discovery(MockDistro(), "idontexist")

        self.assertIn(
            "Skip dhcp_discovery: nic idontexist not found in get_devicelist.",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.subp.which")
    @mock.patch("cloudinit.net.dhcp.find_fallback_nic")
    def test_absent_dhclient_command(self, m_fallback, m_which):
        """When dhclient doesn't exist in the OS, log the issue and no-op."""
        m_fallback.return_value = "eth9"
        m_which.return_value = None  # dhclient isn't found

        with pytest.raises(NoDHCPLeaseMissingDhclientError):
            maybe_perform_dhcp_discovery(MockDistro())

        self.assertIn(
            "Skip dhclient configuration: No dhclient command found.",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("time.sleep", mock.MagicMock())
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.net.dhcp.util.wait_for_files", return_value=False)
    def test_dhcp_discovery_warns_invalid_pid(
        self, m_wait, m_which, m_subp, m_kill, m_remove
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
            "cloudinit.util.load_file", return_value=lease_content
        ):
            self.assertCountEqual(
                [
                    {
                        "interface": "eth9",
                        "fixed-address": "192.168.2.74",
                        "subnet-mask": "255.255.255.0",
                        "routers": "192.168.2.1",
                    }
                ],
                IscDhclient.parse_dhcp_lease_file("lease"),
            )
        with self.assertRaises(InvalidDHCPLeaseFileError):
            with mock.patch("cloudinit.util.load_file", return_value=""):
                IscDhclient().dhcp_discovery("eth9", distro=MockDistro())
        self.assertIn(
            "dhclient(pid=, parentpid=unknown) failed "
            "to daemonize after 10.0 seconds",
            self.logs.getvalue(),
        )
        m_kill.assert_not_called()

    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.util.get_proc_ppid")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.util.wait_for_files")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    def test_dhcp_discovery_waits_on_lease_and_pid(
        self, m_subp, m_which, m_wait, m_kill, m_getppid, m_remove
    ):
        """dhcp_discovery waits for the presence of pidfile and dhcp.leases."""
        m_subp.return_value = ("", "")

        # Don't create pid or leases file
        m_wait.return_value = [PID_F]  # Return the missing pidfile wait for
        m_getppid.return_value = 1  # Indicate that dhclient has daemonized
        self.assertEqual(
            [], IscDhclient().dhcp_discovery("eth9", distro=MockDistro())
        )
        self.assertEqual(
            mock.call([PID_F, LEASE_F], maxwait=5, naplen=0.01),
            m_wait.call_args_list[0],
        )
        self.assertIn(
            "WARNING: dhclient did not produce expected files: dhclient.pid",
            self.logs.getvalue(),
        )
        m_kill.assert_not_called()

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=False)
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.util.get_proc_ppid")
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
        m_getppid,
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
        m_getppid.return_value = 1  # Indicate that dhclient has daemonized

        with mock.patch(
            "cloudinit.util.load_file", side_effect=["1", lease_content]
        ):
            self.assertCountEqual(
                [
                    {
                        "interface": "eth9",
                        "fixed-address": "192.168.2.74",
                        "subnet-mask": "255.255.255.0",
                        "routers": "192.168.2.1",
                    }
                ],
                IscDhclient().dhcp_discovery("eth9", distro=MockDistro()),
            )
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
    @mock.patch("cloudinit.net.dhcp.util.get_proc_ppid", return_value=1)
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
        m_getppid,
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
            "cloudinit.util.load_file", side_effect=["1", lease_content]
        ):
            self.assertCountEqual(
                [
                    {
                        "interface": "ib0",
                        "fixed-address": "192.168.2.74",
                        "subnet-mask": "255.255.255.0",
                        "routers": "192.168.2.1",
                    }
                ],
                IscDhclient().dhcp_discovery("ib0", distro=MockDistro()),
            )
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
    @mock.patch("cloudinit.net.dhcp.util.get_proc_ppid")
    @mock.patch("cloudinit.net.dhcp.os.kill")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/dhclient")
    @mock.patch("cloudinit.util.wait_for_files")
    def test_dhcp_output_error_stream(
        self, m_wait, m_which, m_subp, m_kill, m_getppid, m_remove
    ):
        """ "dhcp_log_func is called with the output and error streams of
        dhclient when the callable is passed."""
        dhclient_err = "FAKE DHCLIENT ERROR"
        dhclient_out = "FAKE DHCLIENT OUT"
        m_subp.return_value = (dhclient_out, dhclient_err)
        tmpdir = self.tmp_dir()
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
        m_getppid.return_value = 1  # Indicate that dhclient has daemonized

        def dhcp_log_func(out, err):
            self.assertEqual(out, dhclient_out)
            self.assertEqual(err, dhclient_err)

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
        fake_lease = {
            "interface": "eth9",
            "fixed-address": "192.168.2.2",
            "subnet-mask": "255.255.0.0",
        }
        m_dhcp.return_value = [fake_lease]
        m_subp.return_value = ("", "")

        self.responses.add(responses.GET, url, body=b"", status=404)
        with EphemeralDHCPv4(
            MockDistro(),
            connectivity_url_data={"url": url},
        ) as lease:
            self.assertEqual(fake_lease, lease)
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

    @mock.patch("cloudinit.net.dhcp.subp.which")
    @mock.patch("cloudinit.net.dhcp.find_fallback_nic")
    def test_absent_udhcpc_command(self, m_fallback, m_which):
        """When dhclient doesn't exist in the OS, log the issue and no-op."""
        m_fallback.return_value = "eth9"
        m_which.return_value = None  # udhcpc isn't found

        distro = MockDistro()
        distro.dhcp_client_priority = [Udhcpc]

        with pytest.raises(NoDHCPLeaseMissingDhclientError):
            maybe_perform_dhcp_discovery(distro)

        self.assertIn(
            "Skip udhcpc configuration: No udhcpc command found.",
            self.logs.getvalue(),
        )

    @mock.patch("cloudinit.net.dhcp.is_ib_interface", return_value=False)
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/udhcpc")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_file")
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
            [
                {
                    "fixed-address": "192.168.2.74",
                    "interface": "eth9",
                    "routers": "192.168.2.1",
                    "static_routes": [
                        ("10.240.0.1/32", "0.0.0.0"),
                        ("0.0.0.0/0", "10.240.0.1"),
                    ],
                    "subnet-mask": "255.255.255.0",
                }
            ],
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
    @mock.patch("cloudinit.net.dhcp.get_ib_interface_hwaddr")
    @mock.patch("cloudinit.net.dhcp.subp.which", return_value="/sbin/udhcpc")
    @mock.patch("cloudinit.net.dhcp.os.remove")
    @mock.patch("cloudinit.net.dhcp.subp.subp")
    @mock.patch("cloudinit.util.load_json")
    @mock.patch("cloudinit.util.load_file")
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
        m_get_ib_interface_hwaddr.return_value = "00:21:28:00:01:cf:4b:01"
        self.assertEqual(
            [
                {
                    "fixed-address": "192.168.2.74",
                    "interface": "ib0",
                    "routers": "192.168.2.1",
                    "static_routes": [
                        ("10.240.0.1/32", "0.0.0.0"),
                        ("0.0.0.0/0", "10.240.0.1"),
                    ],
                    "subnet-mask": "255.255.255.0",
                }
            ],
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
                        "0x3d:0021280001cf4b01",
                    ],
                    update_env={
                        "LEASE_FILE": "/var/tmp/cloud-init/ib0.lease.json"
                    },
                    capture=True,
                ),
            ]
        )
