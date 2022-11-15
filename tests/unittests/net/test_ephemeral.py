# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit.net.ephemeral import EphemeralIPNetwork

M_PATH = "cloudinit.net.ephemeral."


class TestEphemeralIPNetwork:
    @pytest.mark.parametrize("ipv6", [False, True])
    @pytest.mark.parametrize("ipv4", [False, True])
    @mock.patch(M_PATH + "contextlib.ExitStack")
    @mock.patch(M_PATH + "EphemeralIPv6Network")
    @mock.patch(M_PATH + "EphemeralDHCPv4")
    def test_stack_order(
        self,
        m_ephemeral_dhcp_v4,
        m_ephemeral_ip_v6_network,
        m_exit_stack,
        ipv4,
        ipv6,
        tmpdir,
    ):
        interface = object()
        tmp_dir = str(tmpdir)
        with EphemeralIPNetwork(
            interface, ipv4=ipv4, ipv6=ipv6, tmp_dir=tmp_dir
        ):
            pass
        expected_call_args_list = []
        if ipv4:
            expected_call_args_list.append(
                mock.call(m_ephemeral_dhcp_v4.return_value)
            )
            assert [
                mock.call(interface, tmp_dir=tmp_dir)
            ] == m_ephemeral_dhcp_v4.call_args_list
        else:
            assert [] == m_ephemeral_dhcp_v4.call_args_list
        if ipv6:
            expected_call_args_list.append(
                mock.call(m_ephemeral_ip_v6_network.return_value)
            )
            assert [
                mock.call(interface)
            ] == m_ephemeral_ip_v6_network.call_args_list
        else:
            assert [] == m_ephemeral_ip_v6_network.call_args_list
        assert (
            expected_call_args_list
            == m_exit_stack.return_value.enter_context.call_args_list
        )
