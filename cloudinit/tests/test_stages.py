# This file is part of cloud-init. See LICENSE file for license information.

"""Tests related to cloudinit.stages module."""

import os

from cloudinit import stages
from cloudinit import sources

from cloudinit.event import EventType
from cloudinit.util import write_file

from cloudinit.tests.helpers import CiTestCase, mock

TEST_INSTANCE_ID = 'i-testing'


class FakeDataSource(sources.DataSource):

    def __init__(self, paths=None, userdata=None, vendordata=None,
                 network_config=''):
        super(FakeDataSource, self).__init__({}, None, paths=paths)
        self.metadata = {'instance-id': TEST_INSTANCE_ID}
        self.userdata_raw = userdata
        self.vendordata_raw = vendordata
        self._network_config = None
        if network_config:   # Permit for None value to setup attribute
            self._network_config = network_config

    @property
    def network_config(self):
        return self._network_config

    def _get_data(self):
        return True


class TestInit(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestInit, self).setUp()
        self.tmpdir = self.tmp_dir()
        self.init = stages.Init()
        # Setup fake Paths for Init to reference
        self.init._cfg = {'system_info': {
            'distro': 'ubuntu', 'paths': {'cloud_dir': self.tmpdir,
                                          'run_dir': self.tmpdir}}}
        self.init.datasource = FakeDataSource(paths=self.init.paths)

    def test_wb__find_networking_config_disabled(self):
        """find_networking_config returns no config when disabled."""
        disable_file = os.path.join(
            self.init.paths.get_cpath('data'), 'upgraded-network')
        write_file(disable_file, '')
        self.assertEqual(
            (None, disable_file),
            self.init._find_networking_config())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_disabled_by_kernel(self, m_cmdline):
        """find_networking_config returns when disabled by kernel cmdline."""
        m_cmdline.return_value = {'config': 'disabled'}
        self.assertEqual(
            (None, 'cmdline'),
            self.init._find_networking_config())
        self.assertEqual('DEBUG: network config disabled by cmdline\n',
                         self.logs.getvalue())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_disabled_by_datasrc(self, m_cmdline):
        """find_networking_config returns when disabled by datasource cfg."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        self.init._cfg = {'system_info': {'paths': {'cloud_dir': self.tmpdir}},
                          'network': {}}  # system config doesn't disable

        self.init.datasource = FakeDataSource(
            network_config={'config': 'disabled'})
        self.assertEqual(
            (None, 'ds'),
            self.init._find_networking_config())
        self.assertEqual('DEBUG: network config disabled by ds\n',
                         self.logs.getvalue())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_disabled_by_sysconfig(self, m_cmdline):
        """find_networking_config returns when disabled by system config."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        self.init._cfg = {'system_info': {'paths': {'cloud_dir': self.tmpdir}},
                          'network': {'config': 'disabled'}}
        self.assertEqual(
            (None, 'system_cfg'),
            self.init._find_networking_config())
        self.assertEqual('DEBUG: network config disabled by system_cfg\n',
                         self.logs.getvalue())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_returns_kernel(self, m_cmdline):
        """find_networking_config returns kernel cmdline config if present."""
        expected_cfg = {'config': ['fakekernel']}
        m_cmdline.return_value = expected_cfg
        self.init._cfg = {'system_info': {'paths': {'cloud_dir': self.tmpdir}},
                          'network': {'config': ['fakesys_config']}}
        self.init.datasource = FakeDataSource(
            network_config={'config': ['fakedatasource']})
        self.assertEqual(
            (expected_cfg, 'cmdline'),
            self.init._find_networking_config())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_returns_system_cfg(self, m_cmdline):
        """find_networking_config returns system config when present."""
        m_cmdline.return_value = {}  # No kernel network config
        expected_cfg = {'config': ['fakesys_config']}
        self.init._cfg = {'system_info': {'paths': {'cloud_dir': self.tmpdir}},
                          'network': expected_cfg}
        self.init.datasource = FakeDataSource(
            network_config={'config': ['fakedatasource']})
        self.assertEqual(
            (expected_cfg, 'system_cfg'),
            self.init._find_networking_config())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_returns_datasrc_cfg(self, m_cmdline):
        """find_networking_config returns datasource net config if present."""
        m_cmdline.return_value = {}  # No kernel network config
        # No system config for network in setUp
        expected_cfg = {'config': ['fakedatasource']}
        self.init.datasource = FakeDataSource(network_config=expected_cfg)
        self.assertEqual(
            (expected_cfg, 'ds'),
            self.init._find_networking_config())

    @mock.patch('cloudinit.stages.cmdline.read_kernel_cmdline_config')
    def test_wb__find_networking_config_returns_fallback(self, m_cmdline):
        """find_networking_config returns fallback config if not defined."""
        m_cmdline.return_value = {}  # Kernel doesn't disable networking
        # Neither datasource nor system_info disable or provide network

        fake_cfg = {'config': [{'type': 'physical', 'name': 'eth9'}],
                    'version': 1}

        def fake_generate_fallback():
            return fake_cfg

        # Monkey patch distro which gets cached on self.init
        distro = self.init.distro
        distro.generate_fallback_config = fake_generate_fallback
        self.assertEqual(
            (fake_cfg, 'fallback'),
            self.init._find_networking_config())
        self.assertNotIn('network config disabled', self.logs.getvalue())

    def test_apply_network_config_disabled(self):
        """Log when network is disabled by upgraded-network."""
        disable_file = os.path.join(
            self.init.paths.get_cpath('data'), 'upgraded-network')

        def fake_network_config():
            return (None, disable_file)

        self.init._find_networking_config = fake_network_config

        self.init.apply_network_config(True)
        self.assertIn(
            'INFO: network config is disabled by %s' % disable_file,
            self.logs.getvalue())

    @mock.patch('cloudinit.distros.ubuntu.Distro')
    def test_apply_network_on_new_instance(self, m_ubuntu):
        """Call distro apply_network_config methods on is_new_instance."""
        net_cfg = {
            'version': 1, 'config': [
                {'subnets': [{'type': 'dhcp'}], 'type': 'physical',
                 'name': 'eth9', 'mac_address': '42:42:42:42:42:42'}]}

        def fake_network_config():
            return net_cfg, 'fallback'

        self.init._find_networking_config = fake_network_config
        self.init.apply_network_config(True)
        self.init.distro.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_called_with(
            net_cfg, bring_up=True)

    @mock.patch('cloudinit.distros.ubuntu.Distro')
    def test_apply_network_on_same_instance_id(self, m_ubuntu):
        """Only call distro.apply_network_config_names on same instance id."""
        old_instance_id = os.path.join(
            self.init.paths.get_cpath('data'), 'instance-id')
        write_file(old_instance_id, TEST_INSTANCE_ID)
        net_cfg = {
            'version': 1, 'config': [
                {'subnets': [{'type': 'dhcp'}], 'type': 'physical',
                 'name': 'eth9', 'mac_address': '42:42:42:42:42:42'}]}

        def fake_network_config():
            return net_cfg, 'fallback'

        self.init._find_networking_config = fake_network_config
        self.init.apply_network_config(True)
        self.init.distro.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_not_called()
        self.assertIn(
            'No network config applied. Neither a new instance'
            " nor datasource network update on '%s' event" % EventType.BOOT,
            self.logs.getvalue())

    @mock.patch('cloudinit.distros.ubuntu.Distro')
    def test_apply_network_on_datasource_allowed_event(self, m_ubuntu):
        """Apply network if datasource.update_metadata permits BOOT event."""
        old_instance_id = os.path.join(
            self.init.paths.get_cpath('data'), 'instance-id')
        write_file(old_instance_id, TEST_INSTANCE_ID)
        net_cfg = {
            'version': 1, 'config': [
                {'subnets': [{'type': 'dhcp'}], 'type': 'physical',
                 'name': 'eth9', 'mac_address': '42:42:42:42:42:42'}]}

        def fake_network_config():
            return net_cfg, 'fallback'

        self.init._find_networking_config = fake_network_config
        self.init.datasource = FakeDataSource(paths=self.init.paths)
        self.init.datasource.update_events = {'network': [EventType.BOOT]}
        self.init.apply_network_config(True)
        self.init.distro.apply_network_config_names.assert_called_with(net_cfg)
        self.init.distro.apply_network_config.assert_called_with(
            net_cfg, bring_up=True)

# vi: ts=4 expandtab
