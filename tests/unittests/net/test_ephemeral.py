# This file is part of cloud-init. See LICENSE file for license information.

import threading
import time
from unittest import mock

import pytest

from cloudinit.net import ephemeral as ephemeral_mod
from cloudinit.net.dhcp import Dhcpcd, IscDhclient, NoDHCPLeaseError
from cloudinit.net.ephemeral import (
    EphemeralDHCPv6,
    EphemeralIPNetwork,
    EphemeralIPv6Network,
)
from cloudinit.subp import ProcessExecutionError
from cloudinit.url_helper import UrlError
from tests.unittests.helpers import does_not_raise
from tests.unittests.util import MockDistro

M_PATH = "cloudinit.net.ephemeral."


class TestEphemeralIPNetwork:
    @pytest.mark.parametrize(
        "ipv6",
        [
            pytest.param(False, id="no_ipv6"),
            pytest.param(True, id="ipv6"),
        ],
    )
    @pytest.mark.parametrize(
        "ipv4",
        [
            pytest.param(False, id="no_ipv4"),
            pytest.param(True, id="ipv4"),
        ],
    )
    @pytest.mark.parametrize(
        "has_connectivity",
        [
            pytest.param(True, id="has_connectivity"),
            pytest.param(False, id="no_connectivity"),
        ],
    )
    @mock.patch(M_PATH + "contextlib.ExitStack")
    @mock.patch(M_PATH + "EphemeralIPv6Network")
    @mock.patch(M_PATH + "EphemeralDHCPv4")
    def test_stack_order(
        self,
        m_ephemeral_dhcp_v4,
        m_ephemeral_ip_v6_network,
        m_exit_stack,
        has_connectivity,
        ipv4,
        ipv6,
        caplog,
    ):
        interface = object()
        distro = MockDistro()
        with mock.patch(
            M_PATH + "_check_connectivity_to_imds"
        ) as m_check_connectivity_to_imds:
            m_check_connectivity_to_imds.return_value = (
                "http://fake_url" if has_connectivity else None
            )
            with EphemeralIPNetwork(
                distro,
                interface,
                ipv4=ipv4,
                ipv6=ipv6,
                connectivity_urls_data=[{"url": "http://fake_url"}],
            ) as ephemeral_net:
                pass
        # assert that the connectivity check was called if either ipv4 or ipv6
        # is enabled (__enter__ exits early if both are disabled)
        if ipv4 or ipv6:
            m_check_connectivity_to_imds.assert_called_once()
            # check caplog for appropriate messages based on connectivity
            if has_connectivity:
                url = "http://fake_url"
                assert (
                    f"We already have connectivity to IMDS at {url}"
                    ", skipping DHCP." in caplog.text
                )
            else:
                assert (
                    "No connectivity to IMDS, attempting DHCP setup."
                    in caplog.text
                )

        expected_call_args_list = []
        # ipv4 should only be attempted if it is enabled and there is no
        # connectivity before the ephemeral network is brought up
        if ipv4 and not has_connectivity:
            expected_call_args_list.append(
                mock.call(m_ephemeral_dhcp_v4.return_value)
            )
            assert [
                mock.call(
                    distro=distro,
                    iface=interface,
                )
            ] == m_ephemeral_dhcp_v4.call_args_list
        # otherwise, assert that ephemeral_dhcp_v4 was not called
        else:
            assert [] == m_ephemeral_dhcp_v4.call_args_list

        # likewise, ipv6 should only be attempted if it is enabled and there is
        # no connectivity before the ephemeral network is brought up
        if ipv6 and not has_connectivity:
            expected_call_args_list.append(
                mock.call(m_ephemeral_ip_v6_network.return_value)
            )
            assert [
                mock.call(distro, interface)
            ] == m_ephemeral_ip_v6_network.call_args_list
        else:
            assert [] == m_ephemeral_ip_v6_network.call_args_list

        assert (
            expected_call_args_list
            == m_exit_stack.return_value.enter_context.call_args_list
        )
        # if we had to bring up ephemeral ipv6 and we have no ipv4,
        # the state message should reflect that we are using link-local ipv6
        if ipv6 and (not ipv4 and not has_connectivity):
            assert "using link-local ipv6" == ephemeral_net.state_msg

    @pytest.mark.parametrize(
        "m_v4, m_v6, m_context, m_side_effects",
        [
            pytest.param(
                False, True, does_not_raise(), [None, None], id="v6_only"
            ),
            pytest.param(
                True, False, does_not_raise(), [None, None], id="v4_only"
            ),
            pytest.param(
                True,
                True,
                does_not_raise(),
                [ProcessExecutionError, None],
                id="v4_error",
            ),
            pytest.param(
                True,
                True,
                does_not_raise(),
                [None, ProcessExecutionError],
                id="v6_error",
            ),
            pytest.param(
                True,
                True,
                pytest.raises(ProcessExecutionError),
                [
                    ProcessExecutionError,
                    ProcessExecutionError,
                ],
                id="v4_v6_error",
            ),
        ],
    )
    def test_interface_init_failures(
        self, m_v4, m_v6, m_context, m_side_effects, mocker
    ):
        mocker.patch(
            "cloudinit.net.ephemeral.EphemeralDHCPv4"
        ).return_value.__enter__.side_effect = m_side_effects[0]
        mocker.patch(
            "cloudinit.net.ephemeral.EphemeralIPv6Network"
        ).return_value.__enter__.side_effect = m_side_effects[1]
        distro = MockDistro()
        with m_context:
            with EphemeralIPNetwork(distro, "eth0", ipv4=m_v4, ipv6=m_v6):
                pass

    @pytest.mark.parametrize(
        [
            "connectivity_urls_data",
            "has_connectivity",
        ],
        [
            pytest.param(
                [{"url": "http://fake_url"}],
                True,
                id="basic_has_connectivity",
            ),
            pytest.param(
                [{"url": "http://fake_url"}],
                False,
                id="basic_no_connectivity",
            ),
            pytest.param(
                [],
                None,
                id="exits_early_no_urls",
            ),
            pytest.param(
                [{"url": "http://fake_url"}],
                False,
                id="basic_url_error",
            ),
            pytest.param(
                [
                    {"url": "http://fake_url"},
                    {"url": "http://fake_url2", "headers": {"key": "value"}},
                ],
                True,
                id="headers_has_connectivity",
            ),
        ],
    )
    # mock out _do_ipv4 and _do_ipv6
    @mock.patch(
        M_PATH + "EphemeralIPNetwork._perform_ephemeral_network_setup",
        return_value=(True, None),
    )
    @mock.patch(
        M_PATH + "EphemeralIPNetwork._perform_ephemeral_network_setup",
        return_value=(True, None),
    )
    def test_check_connectivity_to_imds(
        self,
        m_do_ipv6,
        m_do_ipv4,
        connectivity_urls_data,
        has_connectivity,
        caplog,
    ):

        def wait_for_url_side_effect(
            urls,
            headers_cb,
            timeout,
            connect_synchronously,
            max_wait,
        ):
            assert urls == [
                url_data["url"] for url_data in connectivity_urls_data
            ]
            for entry in connectivity_urls_data:
                assert headers_cb(entry["url"]) == entry.get("headers")
            if not has_connectivity:
                raise UrlError("fake error")
            return urls[0], b"{}"

        # how wait_for_url is imported in the module:
        # from cloudinit.url_helper import UrlError, wait_for_url

        distro = MockDistro()
        with mock.patch(M_PATH + "wait_for_url") as m_wait_for_url:
            m_wait_for_url.side_effect = wait_for_url_side_effect
            with EphemeralIPNetwork(
                distro,
                "eth0",
                connectivity_urls_data=connectivity_urls_data,
            ):
                pass

        if not connectivity_urls_data:
            assert not m_wait_for_url.called
        elif has_connectivity:
            assert m_wait_for_url.called
        else:
            assert (
                "Failed to reach IMDS without ephemeral network setup: "
                "fake error" in caplog.text
            )
            assert m_wait_for_url.called
        # check caplog for appropriate messages based on connectivity
        if has_connectivity:
            url = [url_data["url"] for url_data in connectivity_urls_data][0]
            assert (
                f"We already have connectivity to IMDS at {url}, "
                "skipping DHCP." in caplog.text
            )
        else:
            assert (
                "No connectivity to IMDS, attempting DHCP setup."
                in caplog.text
            )

    @mock.patch(M_PATH + "wait_for_url")
    def test_connectivity_filters_address_family_and_request_method(
        self, m_wait_for_url
    ):
        ipv6_url = "http://[fd00:100::100:200]/latest/api/token"
        urls_data = [
            {
                "url": "http://100.100.100.200/latest/api/token",
                "headers": {"token-ttl": "21600"},
                "request_method": "PUT",
                "ip_version": "ipv4",
            },
            {
                "url": ipv6_url,
                "headers": {"token-ttl": "21600"},
                "request_method": "PUT",
                "ip_version": "ipv6",
            },
        ]
        m_wait_for_url.return_value = (ipv6_url, b"token")

        assert (
            ephemeral_mod._check_connectivity_to_imds(
                urls_data, ip_version="ipv6"
            )
            == ipv6_url
        )

        kwargs = m_wait_for_url.call_args.kwargs
        assert kwargs["urls"] == [ipv6_url]
        assert kwargs["request_method"] == "PUT"
        assert kwargs["headers_cb"](ipv6_url) == {"token-ttl": "21600"}


class TestEphemeralIPv6Network:
    LL = "fe80" + "0" * 28  # a link-local address, hex, unprefixed

    def _row(self, flags, scope="20", dev="eth0"):
        return [self.LL, "02", "40", scope, flags, dev]

    def test_link_up_only_without_enable_ra(self):
        """Default path: bring the link up, touch no sysctl, no DAD wait."""
        distro = MockDistro()
        with mock.patch(
            M_PATH + "net.read_sys_net", return_value="down"
        ), mock.patch.object(
            distro.net_ops, "link_up"
        ) as m_link_up, mock.patch.object(
            EphemeralIPv6Network, "_apply_ra_sysctls"
        ) as m_apply, mock.patch.object(
            EphemeralIPv6Network, "wait_for_link_local"
        ) as m_wait:
            with EphemeralIPv6Network(distro, "eth0"):
                pass
        m_apply.assert_not_called()
        m_wait.assert_not_called()
        m_link_up.assert_called_once_with("eth0")

    def test_enable_ra_sets_and_restores_sysctls(self):
        """accept_ra is turned on before link-up and put back on exit."""
        original = {
            "disable_ipv6": "0",
            "accept_ra": "0",
            "accept_ra_defrtr": "0",
        }
        written: dict = {}
        eph = EphemeralIPv6Network(MockDistro(), "eth0", enable_ra=True)
        with mock.patch(
            M_PATH + "net.read_sys_net", return_value="up"
        ), mock.patch.object(
            eph, "_read_sysctl", side_effect=original.get
        ), mock.patch.object(
            eph, "wait_for_link_local", return_value=True
        ), mock.patch.object(
            eph,
            "_write_sysctl",
            side_effect=lambda k, v: written.setdefault(k, []).append(v)
            or True,
        ):
            eph.__enter__()
            # disable_ipv6 already matched, so only the two that differed
            # were changed and remembered.
            assert {"accept_ra": "0", "accept_ra_defrtr": "0"} == (
                eph.restore_sysctls
            )
            assert written["accept_ra"] == ["2"]
            eph.__exit__()
            assert written["accept_ra"] == ["2", "0"]

    def test_wait_for_link_local_skips_tentative(self):
        # flags 0x40 = tentative (not ready), then 0x80 = permanent (ready)
        with mock.patch(
            M_PATH + "_read_if_inet6",
            side_effect=[[self._row("40")], [self._row("80")]],
        ), mock.patch(M_PATH + "time.sleep"):
            eph = EphemeralIPv6Network(MockDistro(), "eth0", enable_ra=True)
            assert eph.wait_for_link_local(max_wait=5, interval=0) is True

    def test_wait_for_link_local_ignores_other_iface_and_scope(self):
        rows = [
            self._row("80", dev="eth1"),  # ready but wrong interface
            self._row("80", scope="00"),  # right interface, global scope
        ]
        with mock.patch(M_PATH + "_read_if_inet6", return_value=rows):
            eph = EphemeralIPv6Network(MockDistro(), "eth0", enable_ra=True)
            assert eph.wait_for_link_local(max_wait=0, interval=0) is False


class CapableClient:
    """Stand-in for a DHCP client that implements DHCPv6."""

    client_name = "dhclient"

    def dhcp6_discovery(self, *_args, **_kwargs):
        return "2408:4002:30bf:6d16::1"


class TestEphemeralDHCPv6:
    ADDR = "2408:4002:30bf:6d16::1"
    CIDR = ADDR + "/128"

    def _client(self, **kw):
        distro = MockDistro()
        client = mock.Mock()
        client.client_name = "dhclient"
        client.dhcp6_discovery.return_value = self.ADDR
        client.dhcp6_prefix = 128
        distro._client = client
        return EphemeralDHCPv6(distro, "eth0", **kw)

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    @mock.patch(M_PATH + "subp.subp")
    def test_obtain_lease_configures_128_with_nodad(self, m_subp, m_conn):
        eph = self._client()
        eph.distro.dhcp_client.dhcp6_discovery.return_value = self.ADDR
        eph.distro.dhcp_client.dhcp6_prefix = 128
        assert self.ADDR == eph.obtain_lease()
        assert [
            "ip",
            "-6",
            "addr",
            "add",
            self.CIDR,
            "dev",
            "eth0",
            "nodad",
        ] == m_subp.call_args_list[0][0][0]

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    @mock.patch(M_PATH + "subp.subp")
    def test_exit_removes_configured_address(self, m_subp, m_conn):
        eph = self._client()
        eph.distro.dhcp_client.dhcp6_discovery.return_value = self.ADDR
        eph.distro.dhcp_client.dhcp6_prefix = 128
        with eph as addr:
            assert addr == self.ADDR
        assert [
            "ip",
            "-6",
            "addr",
            "del",
            self.CIDR,
            "dev",
            "eth0",
        ] == m_subp.call_args_list[-1][0][0]

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    @mock.patch(M_PATH + "subp.subp")
    def test_preexisting_address_is_not_torn_down(self, m_subp, m_conn):
        """An address we did not add must not be removed on exit."""
        eph = self._client()
        eph.distro.dhcp_client.dhcp6_discovery.return_value = self.ADDR
        eph.distro.dhcp_client.dhcp6_prefix = 128
        m_subp.side_effect = ProcessExecutionError(
            stderr="Error: ipv6: address already assigned."
        )
        eph.obtain_lease()
        assert eph.cleanup_cmds == []
        eph.clean_network()  # must be a no-op, not a spurious del

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    def test_falls_back_to_a_client_that_can_do_dhcp6(self, m_conn):
        """A preferred client without DHCPv6 must not disable IPv6.

        udhcpc, for one, cannot solicit DHCPv6, so falling back to any
        installed client that can keeps IPv6 usable while the preferred
        client still handles IPv4.
        """
        eph = self._client()
        preferred = mock.Mock(spec=["client_name"])
        preferred.client_name = "udhcpc"
        eph.distro._client = preferred
        with mock.patch(M_PATH + "ALL_DHCP_CLIENTS", [CapableClient]):
            assert isinstance(eph._select_client(), CapableClient)

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    def test_raises_when_no_client_can_do_dhcp6(self, m_conn):
        """With nothing installed that can solicit, fail cleanly."""
        eph = self._client()
        preferred = mock.Mock(spec=["client_name"])
        preferred.client_name = "udhcpc"
        eph.distro._client = preferred
        with mock.patch(M_PATH + "ALL_DHCP_CLIENTS", []):
            with pytest.raises(NoDHCPLeaseError):
                eph.obtain_lease()

    @mock.patch(M_PATH + "_check_connectivity_to_imds", return_value=None)
    def test_preferred_client_is_kept_when_capable(self, m_conn):
        """No fallback when the distro's own client can do DHCPv6."""
        eph = self._client()
        preferred = mock.Mock()
        preferred.client_name = "dhclient"
        preferred.dhcp6_discovery = mock.Mock(return_value=self.ADDR)
        eph.distro._client = preferred
        assert eph._select_client() is preferred


class TestReapStragglers:
    """The losing family's client is stopped without hitting other clients."""

    def _net(self, client):
        distro = MockDistro()
        distro._client = client
        return EphemeralIPNetwork(distro, "eth0")

    @mock.patch(M_PATH + "subp.subp")
    def test_dhcpcd_reaps_only_losing_family_by_pid(self, m_subp):
        """Dhcpcd stops the loser by pidfile instead of command matching."""
        with mock.patch("cloudinit.net.dhcp.subp.which", return_value=True):
            client = Dhcpcd()
        eph = self._net(client)
        eph._race_winner = "ipv6"
        with mock.patch.object(client, "stop_ephemeral") as m_stop:
            eph._reap_stragglers()
        m_stop.assert_called_once_with("eth0", "ipv4", eph.distro)
        assert [] == m_subp.call_args_list

    @mock.patch(M_PATH + "subp.subp")
    def test_dhclient_reaped_by_lease_path(self, m_subp):
        """dhclient is matched by its lease files, never the dhcpcd marker."""
        with mock.patch("cloudinit.net.dhcp.subp.which", return_value=True):
            client = IscDhclient()
        self._net(client)._reap_stragglers()
        patterns = [c.args[0][-1] for c in m_subp.call_args_list]
        assert "/run/dhclient.lease" in patterns
        assert "/run/dhclient6.lease" in patterns

    @mock.patch(M_PATH + "subp.subp")
    def test_reap_joins_losing_worker(self, m_subp):
        """The worker exits after its client's process group is stopped."""
        with mock.patch("cloudinit.net.dhcp.subp.which", return_value=True):
            client = Dhcpcd()
        thread = mock.Mock()
        thread.is_alive.return_value = True
        eph = self._net(client)
        eph._race_winner = "ipv6"
        eph._race_threads = {"ipv4": thread}
        with mock.patch.object(client, "stop_ephemeral"):
            eph._reap_stragglers()
        thread.join.assert_called_once_with(timeout=1.0)


@mock.patch(M_PATH + "EphemeralIPNetwork._reap_stragglers")
@mock.patch(M_PATH + "EphemeralDHCPv6")
@mock.patch(M_PATH + "EphemeralIPv6Network")
@mock.patch(M_PATH + "EphemeralDHCPv4")
class TestEphemeralIPNetworkConcurrent:
    """The dhcp6 opt-in path, which sets both families up at once."""

    def _net(self, **kw):
        kw.setdefault("ipv4", True)
        kw.setdefault("ipv6", True)
        kw.setdefault("dhcp6", True)
        return EphemeralIPNetwork(MockDistro(), "eth0", **kw)

    @staticmethod
    def _slow(*_args, **_kwargs):
        """Make one leg lose deterministically without failing."""
        time.sleep(0.2)

    def test_ipv4_preferred_when_both_come_up(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """Whichever family answers first is used; here that is ipv4."""
        m_v6.return_value.__enter__.side_effect = self._slow
        eph = self._net()
        with eph as ret:
            assert ret is eph
        assert eph.state_msg == ""

    def test_ipv6_wins_when_dhcp4_fails(self, m_v4, m_v6net, m_v6, m_reap):
        """An IPv6-only instance: no DHCPv4 server, so IPv6 carries it."""
        m_v4.return_value.__enter__.side_effect = NoDHCPLeaseError()
        eph = self._net()
        with eph as ret:
            assert ret is eph
        assert eph.state_msg == "using ipv6"
        # The IPv6 leg is a lease, not just a link-local address.
        assert m_v6.called

    def test_dhcp4_is_not_delayed_by_a_hanging_dhcp6(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """An IPv4-only instance must not wait out the DHCPv6 client.

        This is the regression the concurrency exists for: soliciting DHCPv6
        where no server answers blocks until the client's own timeout.
        """
        m_v6.return_value.__enter__.side_effect = self._slow
        started = time.monotonic()
        with self._net():
            elapsed = time.monotonic() - started
        assert elapsed < 0.2, "ipv4 waited on the ipv6 leg"

    def test_family_only_wins_after_its_imds_url_answers(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """A configured address without IMDS connectivity cannot win."""
        urls_data = [
            {"url": "http://100.100.100.200/token", "ip_version": "ipv4"},
            {"url": "http://[fd00:100::100:200]/token", "ip_version": "ipv6"},
        ]
        m_v6.return_value.__enter__.side_effect = self._slow
        with mock.patch(
            M_PATH + "_check_connectivity_to_imds",
            side_effect=[None, None, urls_data[1]["url"]],
        ) as m_connectivity:
            eph = self._net(connectivity_urls_data=urls_data)
            with eph:
                pass

        assert eph.state_msg == "using ipv6"
        assert m_connectivity.call_args_list == [
            mock.call(urls_data),
            mock.call(urls_data, ip_version="ipv4"),
            mock.call(urls_data, ip_version="ipv6"),
        ]

    def test_dhcp4_only_when_dhcp6_fails(self, m_v4, m_v6net, m_v6, m_reap):
        """No IPv6 on the link at all: ipv4 still carries the boot."""
        m_v6.return_value.__enter__.side_effect = NoDHCPLeaseError()
        eph = self._net()
        with eph as ret:
            assert ret is eph
        assert eph.state_msg == ""

    def test_raises_when_both_families_fail(self, m_v4, m_v6net, m_v6, m_reap):
        m_v4.return_value.__enter__.side_effect = NoDHCPLeaseError()
        m_v6.return_value.__enter__.side_effect = NoDHCPLeaseError()
        with pytest.raises(NoDHCPLeaseError):
            with self._net():
                pass

    def test_enable_ra_forwarded_to_ipv6_network(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        with self._net(enable_ra=True):
            pass
        assert m_v6net.call_args.kwargs["enable_ra"] is True

    def test_existing_connectivity_skips_race_and_reaping(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """Do not stop an existing client when no race was started."""
        urls_data = [{"url": "http://100.100.100.200/token"}]
        with mock.patch(
            M_PATH + "_check_connectivity_to_imds",
            return_value=urls_data[0]["url"],
        ):
            with self._net(connectivity_urls_data=urls_data):
                pass
        m_v4.assert_not_called()
        m_v6.assert_not_called()
        m_reap.assert_not_called()

    def test_exit_reaps_losing_client(self, m_v4, m_v6net, m_v6, m_reap):
        """A client still soliciting for the losing family is stopped."""
        with self._net():
            pass
        assert m_reap.called

    def test_late_successful_family_closes_its_own_stack(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """A family finishing after the race cannot leak its context stack."""
        eph = self._net()
        outcomes: dict = {}
        stacks: dict = {}
        lock = threading.Lock()
        progress = threading.Event()
        race_done = threading.Event()
        race_done.set()

        eph._setup_family("ipv6", outcomes, stacks, lock, progress, race_done)

        assert outcomes == {}
        assert stacks == {}
        assert progress.is_set()
        m_v6.return_value.__exit__.assert_called_once()
        m_v6net.return_value.__exit__.assert_called_once()

    def test_without_dhcp6_serial_path_is_used(
        self, m_v4, m_v6net, m_v6, m_reap
    ):
        """Not opting in must not reach the concurrent path at all."""
        eph = EphemeralIPNetwork(MockDistro(), "eth0", ipv4=True, ipv6=True)
        with mock.patch.object(eph, "_enter_concurrent") as m_conc:
            with mock.patch(
                M_PATH + "_check_connectivity_to_imds", return_value=None
            ):
                with eph:
                    pass
        m_conc.assert_not_called()
        assert not m_reap.called
