from collections import namedtuple
from unittest.mock import patch

import pytest

from cloudinit.net.configurers import (
    DEFAULT_PRIORITY,
    search_configurer,
    select_configurer,
)
from cloudinit.net.ifupdown import IfUpDownConfigurer
from cloudinit.net.netplan import NetplanConfigurer
from cloudinit.net.network_manager import NetworkManagerConfigurer
from cloudinit.net.network_state import parse_net_config_data
from cloudinit.safeyaml import load


V1_CONFIG = """\
version: 1
config:
- type: physical
  name: eth0
- type: physical
  name: eth1
"""

V2_CONFIG = """\
version: 2
ethernets:
  eth0:
    dhcp4: true
  eth1:
    dhcp4: true
"""

IF_UP_DOWN_AVAILABLE_CALLS = [
    (('ifquery',), {'search': ['/sbin', '/usr/sbin'], 'target': None}),
    (('ifup',), {'search': ['/sbin', '/usr/sbin'], 'target': None}),
    (('ifdown',), {'search': ['/sbin', '/usr/sbin'], 'target': None}),
]

IF_UP_DOWN_CALL_LIST = [
    ((['ifup', 'eth0'], ), {}),
    ((['ifup', 'eth1'], ), {}),
]

NETPLAN_AVAILABLE_CALLS = [
    (('netplan',), {'search': ['/usr/sbin', '/sbin'], 'target': None}),
]

NETPLAN_CALL_LIST = [
    ((['netplan', 'apply'], ), {'capture': True}),
]

NETWORK_MANAGER_AVAILABLE_CALLS = [
    (('nmcli',), {'target': None}),
]

NETWORK_MANAGER_CALL_LIST = [
    ((['nmcli', 'connection', 'up', 'eth0'], ), {}),
    ((['nmcli', 'connection', 'up', 'eth1'], ), {}),
]


@pytest.yield_fixture
def available_mocks():
    mocks = namedtuple('Mocks', 'm_which, m_file')
    with patch('cloudinit.subp.which', return_value=True) as m_which:
        with patch('os.path.isfile', return_value=True) as m_file:
            yield mocks(m_which, m_file)


@pytest.yield_fixture
def unavailable_mocks():
    mocks = namedtuple('Mocks', 'm_which, m_file')
    with patch('cloudinit.subp.which', return_value=False) as m_which:
        with patch('os.path.isfile', return_value=False) as m_file:
            yield mocks(m_which, m_file)


class TestSearchAndSelect:
    def test_defaults(self, available_mocks):
        resp = search_configurer()
        assert resp == DEFAULT_PRIORITY

        configurer = select_configurer()
        assert configurer == DEFAULT_PRIORITY[0]

    def test_priority(self, available_mocks):
        new_order = [NetplanConfigurer, NetworkManagerConfigurer]
        resp = search_configurer(priority=new_order)
        assert resp == new_order

        configurer = select_configurer(priority=new_order)
        assert configurer == new_order[0]

    def test_target(self, available_mocks):
        search_configurer(target='/tmp')
        assert '/tmp' == available_mocks.m_which.call_args[1]['target']

        select_configurer(target='/tmp')
        assert '/tmp' == available_mocks.m_which.call_args[1]['target']

    @patch('cloudinit.net.ifupdown.IfUpDownConfigurer.available',
           return_value=False)
    def test_first_not_available(self, m_available):
        resp = search_configurer()
        assert resp == DEFAULT_PRIORITY[1:]

        resp = select_configurer()
        assert resp == DEFAULT_PRIORITY[1]

    def test_priority_not_exist(self, available_mocks):
        with pytest.raises(ValueError):
            search_configurer(priority=['spam', 'eggs'])
        with pytest.raises(ValueError):
            select_configurer(priority=['spam', 'eggs'])

    def test_none_available(self, unavailable_mocks):
        resp = search_configurer()
        assert resp == []

        with pytest.raises(RuntimeError):
            select_configurer()


@pytest.mark.parametrize('configurer, available_calls, expected_call_list', [
    (IfUpDownConfigurer, IF_UP_DOWN_AVAILABLE_CALLS, IF_UP_DOWN_CALL_LIST),
    (NetplanConfigurer, NETPLAN_AVAILABLE_CALLS, NETPLAN_CALL_LIST),
    (NetworkManagerConfigurer, NETWORK_MANAGER_AVAILABLE_CALLS,
     NETWORK_MANAGER_CALL_LIST),
])
class TestIfUpDownConfigurer:
    def test_available(
        self, configurer, available_calls, expected_call_list, available_mocks
    ):
        configurer.available()
        assert available_mocks.m_which.call_args_list == available_calls

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_interface(
        self, m_subp, configurer, available_calls, expected_call_list,
        available_mocks
    ):
        configurer.bring_up_interface('eth0')
        assert len(m_subp.call_args_list) == 1
        assert m_subp.call_args_list[0] == expected_call_list[0]

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_interfaces(
        self, m_subp, configurer, available_calls, expected_call_list,
        available_mocks
    ):
        configurer.bring_up_interfaces(['eth0', 'eth1'])
        assert expected_call_list == m_subp.call_args_list

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_all_interfaces_v1(
        self, m_subp, configurer, available_calls, expected_call_list,
        available_mocks
    ):
        network_state = parse_net_config_data(load(V1_CONFIG))
        configurer.bring_up_all_interfaces(network_state)
        for call in m_subp.call_args_list:
            assert call in expected_call_list

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_all_interfaces_v2(
        self, m_subp, configurer, available_calls, expected_call_list,
        available_mocks
    ):
        network_state = parse_net_config_data(load(V2_CONFIG))
        configurer.bring_up_all_interfaces(network_state)
        for call in m_subp.call_args_list:
            assert call in expected_call_list
