# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.net.ephemeral import EphemeralIPNetwork
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
