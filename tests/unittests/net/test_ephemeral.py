# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.net.ephemeral import EphemeralIPNetwork
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import does_not_raise
from tests.unittests.util import MockDistro

M_PATH = "cloudinit.net.ephemeral."


class TestEphemeralIPNetwork:
    @pytest.mark.parametrize("ipv6", [False, True])
    @pytest.mark.parametrize("ipv4", [False, True])
    @pytest.mark.parametrize(
        "connectivity_urls_data", [None, [{"url": "foo"}]]
    )
    @mock.patch(M_PATH + "contextlib.ExitStack")
    @mock.patch(M_PATH + "EphemeralIPv6Network")
    @mock.patch(M_PATH + "EphemeralDHCPv4")
    def test_stack_order(
        self,
        m_ephemeral_dhcp_v4,
        m_ephemeral_ip_v6_network,
        m_exit_stack,
        connectivity_urls_data,
        ipv4,
        ipv6,
    ):
        interface = object()
        distro = MockDistro()
        with EphemeralIPNetwork(
            distro,
            interface,
            ipv4=ipv4,
            ipv6=ipv6,
            connectivity_urls_data=connectivity_urls_data,
        ):
            pass
        expected_call_args_list = []
        if ipv4:
            expected_call_args_list.append(
                mock.call(m_ephemeral_dhcp_v4.return_value)
            )
            assert [
                mock.call(
                    distro=distro,
                    iface=interface,
                    connectivity_urls_data=connectivity_urls_data,
                )
            ] == m_ephemeral_dhcp_v4.call_args_list
        else:
            assert [] == m_ephemeral_dhcp_v4.call_args_list
        if ipv6:
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

    @pytest.mark.parametrize(
        [
            "ipv4_enabled",
            "ipv6_connectivity",
        ],
        [
            pytest.param(
                True,
                True,
                id="ipv4_enabled_with_ipv6_connectivity",
            ),
            pytest.param(
                False,
                True,
                id="ipv4_disabled_with_ipv6_connectivity",
            ),
            pytest.param(
                False,
                False,
                id="ipv4_disabled_without_ipv6_connectivity",
            ),
            pytest.param(
                True,
                False,
                id="ipv4_enabled_without_ipv6_connectivity",
            ),
        ],
    )
    @mock.patch(M_PATH + "contextlib.ExitStack")
    def test_ipv6_stuff(
        self,
        m_exit_stack,
        ipv4_enabled,
        ipv6_connectivity,
        mocker,
    ):
        """
        Assumes that ipv6_check_callback is always provided and the _do_ipv6
        helper always succeeds and thus ephemeral_obtained is always True.
        """
        m_ipv6_check_callback = mock.MagicMock()
        m_do_ipv6 = mocker.patch(M_PATH + "EphemeralIPNetwork._do_ipv6")
        m_do_ipv4 = mocker.patch(M_PATH + "EphemeralIPNetwork._do_ipv4")
        # always have ipv6 interface be brought up successfully
        m_do_ipv6.return_value = (True, [])
        m_do_ipv4.return_value = (True, [])

        # ipv6 check returns url on success and None on failure
        m_ipv6_check_callback.return_value = (
            "fake_url" if ipv6_connectivity else None
        )

        # check if ipv4 is attempted to be brought up
        # should only be attempted if ipv4 is enabled
        # and ipv6 connectivity is not available
        expected_ipv4_bringup = ipv4_enabled and not ipv6_connectivity

        interface = object()
        distro = MockDistro()
        ephemeral_net = EphemeralIPNetwork(
            distro,
            interface,
            ipv4=ipv4_enabled,
            ipv6=True,
            ipv6_connectivity_check_callback=m_ipv6_check_callback,
        )
        with ephemeral_net:
            pass

        if expected_ipv4_bringup:
            m_do_ipv4.assert_called_once()
        else:
            m_do_ipv4.assert_not_called()

        m_do_ipv6.assert_called_once()
        m_ipv6_check_callback.assert_called_once()
        # assert m_exit_stack.return_value.enter_context.call_count == 2

    @mock.patch(M_PATH + "contextlib.ExitStack")
    def test_ipv6_arg_mismatch_raises_exception(
        self,
        m_exit_stack,
        mocker,
    ):
        """
        Validate that ValueError exception is raised when ipv6 is not enabled
        but ipv6_connectivity_check_callback is provided.
        """
        m_ipv6_check_callback = mock.MagicMock()

        interface = object()
        distro = MockDistro()
        ephemeral_net = EphemeralIPNetwork(
            distro,
            interface,
            ipv4=True,
            # set ipv6 to disabled
            ipv6=False,
            # but provide ipv6_connectivity_check_callback
            ipv6_connectivity_check_callback=m_ipv6_check_callback,
        )
        with pytest.raises(ValueError):
            with ephemeral_net:
                pass

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
