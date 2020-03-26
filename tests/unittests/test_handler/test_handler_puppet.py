# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_puppet
from cloudinit.sources import DataSourceNone
from cloudinit import (distros, helpers, cloud, util)
from cloudinit.tests.helpers import CiTestCase, mock

import logging
import textwrap


LOG = logging.getLogger(__name__)


@mock.patch('cloudinit.config.cc_puppet.util')
@mock.patch('cloudinit.config.cc_puppet.os')
class TestAutostartPuppet(CiTestCase):

    def test_wb_autostart_puppet_updates_puppet_default(self, m_os, m_util):
        """Update /etc/default/puppet to autostart if it exists."""

        def _fake_exists(path):
            return path == '/etc/default/puppet'

        m_os.path.exists.side_effect = _fake_exists
        cc_puppet._autostart_puppet(LOG)
        self.assertEqual(
            [mock.call(['sed', '-i', '-e', 's/^START=.*/START=yes/',
                        '/etc/default/puppet'], capture=False)],
            m_util.subp.call_args_list)

    def test_wb_autostart_pupppet_enables_puppet_systemctl(self, m_os, m_util):
        """If systemctl is present, enable puppet via systemctl."""

        def _fake_exists(path):
            return path == '/bin/systemctl'

        m_os.path.exists.side_effect = _fake_exists
        cc_puppet._autostart_puppet(LOG)
        expected_calls = [mock.call(
            ['/bin/systemctl', 'enable', 'puppet.service'], capture=False)]
        self.assertEqual(expected_calls, m_util.subp.call_args_list)

    def test_wb_autostart_pupppet_enables_puppet_chkconfig(self, m_os, m_util):
        """If chkconfig is present, enable puppet via checkcfg."""

        def _fake_exists(path):
            return path == '/sbin/chkconfig'

        m_os.path.exists.side_effect = _fake_exists
        cc_puppet._autostart_puppet(LOG)
        expected_calls = [mock.call(
            ['/sbin/chkconfig', 'puppet', 'on'], capture=False)]
        self.assertEqual(expected_calls, m_util.subp.call_args_list)


@mock.patch('cloudinit.config.cc_puppet._autostart_puppet')
class TestPuppetHandle(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestPuppetHandle, self).setUp()
        self.new_root = self.tmp_dir()
        self.conf = self.tmp_path('puppet.conf')
        self.csr_attributes_path = self.tmp_path('csr_attributes.yaml')

    def _get_cloud(self, distro):
        paths = helpers.Paths({'templates_dir': self.new_root})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    def test_handler_skips_missing_puppet_key_in_cloudconfig(self, m_auto):
        """Cloud-config containing no 'puppet' key is skipped."""
        mycloud = self._get_cloud('ubuntu')
        cfg = {}
        cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        self.assertIn(
            "no 'puppet' configuration found", self.logs.getvalue())
        self.assertEqual(0, m_auto.call_count)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_puppet_config_starts_puppet_service(self, m_subp, m_auto):
        """Cloud-config 'puppet' configuration starts puppet."""
        mycloud = self._get_cloud('ubuntu')
        cfg = {'puppet': {'install': False}}
        cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        self.assertEqual(1, m_auto.call_count)
        self.assertEqual(
            [mock.call(['service', 'puppet', 'start'], capture=False)],
            m_subp.call_args_list)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_empty_puppet_config_installs_puppet(self, m_subp, m_auto):
        """Cloud-config empty 'puppet' configuration installs latest puppet."""
        mycloud = self._get_cloud('ubuntu')
        mycloud.distro = mock.MagicMock()
        cfg = {'puppet': {}}
        cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        self.assertEqual(
            [mock.call(('puppet', None))],
            mycloud.distro.install_packages.call_args_list)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_puppet_config_installs_puppet_on_true(self, m_subp, _):
        """Cloud-config with 'puppet' key installs when 'install' is True."""
        mycloud = self._get_cloud('ubuntu')
        mycloud.distro = mock.MagicMock()
        cfg = {'puppet': {'install': True}}
        cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        self.assertEqual(
            [mock.call(('puppet', None))],
            mycloud.distro.install_packages.call_args_list)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_puppet_config_installs_puppet_version(self, m_subp, _):
        """Cloud-config 'puppet' configuration can specify a version."""
        mycloud = self._get_cloud('ubuntu')
        mycloud.distro = mock.MagicMock()
        cfg = {'puppet': {'version': '3.8'}}
        cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        self.assertEqual(
            [mock.call(('puppet', '3.8'))],
            mycloud.distro.install_packages.call_args_list)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_puppet_config_updates_puppet_conf(self, m_subp, m_auto):
        """When 'conf' is provided update values in PUPPET_CONF_PATH."""
        mycloud = self._get_cloud('ubuntu')
        cfg = {
            'puppet': {
                'conf': {'agent': {'server': 'puppetmaster.example.org'}}}}
        util.write_file(self.conf, '[agent]\nserver = origpuppet\nother = 3')
        puppet_conf_path = 'cloudinit.config.cc_puppet.PUPPET_CONF_PATH'
        mycloud.distro = mock.MagicMock()
        with mock.patch(puppet_conf_path, self.conf):
            cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        content = util.load_file(self.conf)
        expected = '[agent]\nserver = puppetmaster.example.org\nother = 3\n\n'
        self.assertEqual(expected, content)

    @mock.patch('cloudinit.config.cc_puppet.util.subp')
    def test_handler_puppet_writes_csr_attributes_file(self, m_subp, m_auto):
        """When csr_attributes is provided
            creates file in PUPPET_CSR_ATTRIBUTES_PATH."""
        mycloud = self._get_cloud('ubuntu')
        mycloud.distro = mock.MagicMock()
        cfg = {
            'puppet': {
              'csr_attributes': {
                'custom_attributes': {
                  '1.2.840.113549.1.9.7': '342thbjkt82094y0ut'
                                          'hhor289jnqthpc2290'},
                'extension_requests': {
                  'pp_uuid': 'ED803750-E3C7-44F5-BB08-41A04433FE2E',
                  'pp_image_name': 'my_ami_image',
                  'pp_preshared_key': '342thbjkt82094y0uthhor289jnqthpc2290'}
                }}}
        csr_attributes = 'cloudinit.config.cc_puppet.' \
                         'PUPPET_CSR_ATTRIBUTES_PATH'
        with mock.patch(csr_attributes, self.csr_attributes_path):
            cc_puppet.handle('notimportant', cfg, mycloud, LOG, None)
        content = util.load_file(self.csr_attributes_path)
        expected = textwrap.dedent("""\
            custom_attributes:
              1.2.840.113549.1.9.7: 342thbjkt82094y0uthhor289jnqthpc2290
            extension_requests:
              pp_image_name: my_ami_image
              pp_preshared_key: 342thbjkt82094y0uthhor289jnqthpc2290
              pp_uuid: ED803750-E3C7-44F5-BB08-41A04433FE2E
            """)
        self.assertEqual(expected, content)
