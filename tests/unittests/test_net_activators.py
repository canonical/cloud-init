from collections import namedtuple
from unittest.mock import patch

import pytest

from cloudinit.net.activators import (
    DEFAULT_PRIORITY,
    search_activator,
    select_activator,
)
from cloudinit.net.activators import (
    IfUpDownActivator,
    NetplanActivator,
    NetworkManagerActivator
)
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
        resp = search_activator()
        assert resp == DEFAULT_PRIORITY

        activator = select_activator()
        assert activator == DEFAULT_PRIORITY[0]

    def test_priority(self, available_mocks):
        new_order = [NetplanActivator, NetworkManagerActivator]
        resp = search_activator(priority=new_order)
        assert resp == new_order

        activator = select_activator(priority=new_order)
        assert activator == new_order[0]

    def test_target(self, available_mocks):
        search_activator(target='/tmp')
        assert '/tmp' == available_mocks.m_which.call_args[1]['target']

        select_activator(target='/tmp')
        assert '/tmp' == available_mocks.m_which.call_args[1]['target']

    @patch('cloudinit.net.activators.IfUpDownActivator.available',
           return_value=False)
    def test_first_not_available(self, m_available, available_mocks):
        resp = search_activator()
        assert resp == DEFAULT_PRIORITY[1:]

        resp = select_activator()
        assert resp == DEFAULT_PRIORITY[1]

    def test_priority_not_exist(self, available_mocks):
        with pytest.raises(ValueError):
            search_activator(priority=['spam', 'eggs'])
        with pytest.raises(ValueError):
            select_activator(priority=['spam', 'eggs'])

    def test_none_available(self, unavailable_mocks):
        resp = search_activator()
        assert resp == []

        with pytest.raises(RuntimeError):
            select_activator()


@pytest.mark.parametrize('activator, available_calls, expected_call_list', [
    (IfUpDownActivator, IF_UP_DOWN_AVAILABLE_CALLS, IF_UP_DOWN_CALL_LIST),
    (NetplanActivator, NETPLAN_AVAILABLE_CALLS, NETPLAN_CALL_LIST),
    (NetworkManagerActivator, NETWORK_MANAGER_AVAILABLE_CALLS,
     NETWORK_MANAGER_CALL_LIST),
])
class TestIfUpDownActivator:
    def test_available(
        self, activator, available_calls, expected_call_list, available_mocks
    ):
        activator.available()
        assert available_mocks.m_which.call_args_list == available_calls

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_interface(
        self, m_subp, activator, available_calls, expected_call_list,
        available_mocks
    ):
        activator.bring_up_interface('eth0')
        assert len(m_subp.call_args_list) == 1
        assert m_subp.call_args_list[0] == expected_call_list[0]

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_interfaces(
        self, m_subp, activator, available_calls, expected_call_list,
        available_mocks
    ):
        activator.bring_up_interfaces(['eth0', 'eth1'])
        assert expected_call_list == m_subp.call_args_list

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_all_interfaces_v1(
        self, m_subp, activator, available_calls, expected_call_list,
        available_mocks
    ):
        network_state = parse_net_config_data(load(V1_CONFIG))
        activator.bring_up_all_interfaces(network_state)
        for call in m_subp.call_args_list:
            assert call in expected_call_list

    @patch('cloudinit.subp.subp', return_value=('', ''))
    def test_bring_up_all_interfaces_v2(
        self, m_subp, activator, available_calls, expected_call_list,
        available_mocks
    ):
        network_state = parse_net_config_data(load(V2_CONFIG))
        activator.bring_up_all_interfaces(network_state)
        for call in m_subp.call_args_list:
            assert call in expected_call_list
