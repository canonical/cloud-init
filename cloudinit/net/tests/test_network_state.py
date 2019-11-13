# This file is part of cloud-init. See LICENSE file for license information.

import mock
from cloudinit.net import network_state
from cloudinit.tests.helpers import CiTestCase

netstate_path = 'cloudinit.net.network_state'


class TestNetworkStateParseConfig(CiTestCase):

    def setUp(self):
        super(TestNetworkStateParseConfig, self).setUp()
        nsi_path = netstate_path + '.NetworkStateInterpreter'
        self.add_patch(nsi_path, 'm_nsi')

    def test_missing_version_returns_none(self):
        ncfg = {}
        self.assertEqual(None, network_state.parse_net_config_data(ncfg))

    def test_unknown_versions_returns_none(self):
        ncfg = {'version': 13.2}
        self.assertEqual(None, network_state.parse_net_config_data(ncfg))

    def test_version_2_passes_self_as_config(self):
        ncfg = {'version': 2, 'otherconfig': {}, 'somemore': [1, 2, 3]}
        network_state.parse_net_config_data(ncfg)
        self.assertEqual([mock.call(version=2, config=ncfg)],
                         self.m_nsi.call_args_list)

    def test_valid_config_gets_network_state(self):
        ncfg = {'version': 2, 'otherconfig': {}, 'somemore': [1, 2, 3]}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)

    def test_empty_v1_config_gets_network_state(self):
        ncfg = {'version': 1, 'config': []}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)

    def test_empty_v2_config_gets_network_state(self):
        ncfg = {'version': 2}
        result = network_state.parse_net_config_data(ncfg)
        self.assertNotEqual(None, result)


# vi: ts=4 expandtab
