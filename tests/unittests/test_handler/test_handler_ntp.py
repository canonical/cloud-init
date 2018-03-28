# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_ntp
from cloudinit.sources import DataSourceNone
from cloudinit import (distros, helpers, cloud, util)
from cloudinit.tests.helpers import (
    FilesystemMockingTestCase, mock, skipUnlessJsonSchema)


import os
from os.path import dirname
import shutil

NTP_TEMPLATE = b"""\
## template: jinja
servers {{servers}}
pools {{pools}}
"""

TIMESYNCD_TEMPLATE = b"""\
## template:jinja
[Time]
{% if servers or pools -%}
NTP={% for host in servers|list + pools|list %}{{ host }} {% endfor -%}
{% endif -%}
"""


class TestNtp(FilesystemMockingTestCase):

    with_logs = True

    def setUp(self):
        super(TestNtp, self).setUp()
        self.subp = util.subp
        self.new_root = self.tmp_dir()

    def _get_cloud(self, distro):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({'templates_dir': self.new_root})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_install(self, mock_util):
        """ntp_install installs via install_func when check_exe is absent."""
        mock_util.which.return_value = None  # check_exe not found.
        install_func = mock.MagicMock()
        cc_ntp.install_ntp(install_func, packages=['ntpx'], check_exe='ntpdx')

        mock_util.which.assert_called_with('ntpdx')
        install_func.assert_called_once_with(['ntpx'])

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_install_not_needed(self, mock_util):
        """ntp_install doesn't attempt install when check_exe is found."""
        mock_util.which.return_value = ["/usr/sbin/ntpd"]  # check_exe found.
        install_func = mock.MagicMock()
        cc_ntp.install_ntp(install_func, packages=['ntp'], check_exe='ntpd')
        install_func.assert_not_called()

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_install_no_op_with_empty_pkg_list(self, mock_util):
        """ntp_install calls install_func with empty list"""
        mock_util.which.return_value = None  # check_exe not found
        install_func = mock.MagicMock()
        cc_ntp.install_ntp(install_func, packages=[], check_exe='timesyncd')
        install_func.assert_called_once_with([])

    def test_ntp_rename_ntp_conf(self):
        """When NTP_CONF exists, rename_ntp moves it."""
        ntpconf = self.tmp_path("ntp.conf", self.new_root)
        util.write_file(ntpconf, "")
        with mock.patch("cloudinit.config.cc_ntp.NTP_CONF", ntpconf):
            cc_ntp.rename_ntp_conf()
        self.assertFalse(os.path.exists(ntpconf))
        self.assertTrue(os.path.exists("{0}.dist".format(ntpconf)))

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_reload_ntp_defaults(self, mock_util):
        """Test service is restarted/reloaded (defaults)"""
        service = 'ntp'
        cmd = ['service', service, 'restart']
        cc_ntp.reload_ntp(service)
        mock_util.subp.assert_called_with(cmd, capture=True)

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_reload_ntp_systemd(self, mock_util):
        """Test service is restarted/reloaded (systemd)"""
        service = 'ntp'
        cmd = ['systemctl', 'reload-or-restart', service]
        cc_ntp.reload_ntp(service, systemd=True)
        mock_util.subp.assert_called_with(cmd, capture=True)

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_reload_ntp_systemd_timesycnd(self, mock_util):
        """Test service is restarted/reloaded (systemd/timesyncd)"""
        service = 'systemd-timesycnd'
        cmd = ['systemctl', 'reload-or-restart', service]
        cc_ntp.reload_ntp(service, systemd=True)
        mock_util.subp.assert_called_with(cmd, capture=True)

    def test_ntp_rename_ntp_conf_skip_missing(self):
        """When NTP_CONF doesn't exist rename_ntp doesn't create a file."""
        ntpconf = self.tmp_path("ntp.conf", self.new_root)
        self.assertFalse(os.path.exists(ntpconf))
        with mock.patch("cloudinit.config.cc_ntp.NTP_CONF", ntpconf):
            cc_ntp.rename_ntp_conf()
        self.assertFalse(os.path.exists("{0}.dist".format(ntpconf)))
        self.assertFalse(os.path.exists(ntpconf))

    def test_write_ntp_config_template_from_ntp_conf_tmpl_with_servers(self):
        """write_ntp_config_template reads content from ntp.conf.tmpl.

        It reads ntp.conf.tmpl if present and renders the value from servers
        key. When no pools key is defined, template is rendered using an empty
        list for pools.
        """
        distro = 'ubuntu'
        cfg = {
            'servers': ['192.168.2.1', '192.168.2.2']
        }
        mycloud = self._get_cloud(distro)
        ntp_conf = self.tmp_path("ntp.conf", self.new_root)  # Doesn't exist
        # Create ntp.conf.tmpl
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.write_ntp_config_template(cfg, mycloud, ntp_conf)
        content = util.read_file_or_url('file://' + ntp_conf).contents
        self.assertEqual(
            "servers ['192.168.2.1', '192.168.2.2']\npools []\n",
            content.decode())

    def test_write_ntp_config_template_uses_ntp_conf_distro_no_servers(self):
        """write_ntp_config_template reads content from ntp.conf.distro.tmpl.

        It reads ntp.conf.<distro>.tmpl before attempting ntp.conf.tmpl. It
        renders the value from the keys servers and pools. When no
        servers value is present, template is rendered using an empty list.
        """
        distro = 'ubuntu'
        cfg = {
            'pools': ['10.0.0.1', '10.0.0.2']
        }
        mycloud = self._get_cloud(distro)
        ntp_conf = self.tmp_path('ntp.conf', self.new_root)  # Doesn't exist
        # Create ntp.conf.tmpl which isn't read
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(b'NOT READ: ntp.conf.<distro>.tmpl is primary')
        # Create ntp.conf.tmpl.<distro>
        with open('{0}.{1}.tmpl'.format(ntp_conf, distro), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.write_ntp_config_template(cfg, mycloud, ntp_conf)
        content = util.read_file_or_url('file://' + ntp_conf).contents
        self.assertEqual(
            "servers []\npools ['10.0.0.1', '10.0.0.2']\n",
            content.decode())

    def test_write_ntp_config_template_defaults_pools_when_empty_lists(self):
        """write_ntp_config_template defaults pools servers upon empty config.

        When both pools and servers are empty, default NR_POOL_SERVERS get
        configured.
        """
        distro = 'ubuntu'
        mycloud = self._get_cloud(distro)
        ntp_conf = self.tmp_path('ntp.conf', self.new_root)  # Doesn't exist
        # Create ntp.conf.tmpl
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.write_ntp_config_template({}, mycloud, ntp_conf)
        content = util.read_file_or_url('file://' + ntp_conf).contents
        default_pools = [
            "{0}.{1}.pool.ntp.org".format(x, distro)
            for x in range(0, cc_ntp.NR_POOL_SERVERS)]
        self.assertEqual(
            "servers []\npools {0}\n".format(default_pools),
            content.decode())
        self.assertIn(
            "Adding distro default ntp pool servers: {0}".format(
                ",".join(default_pools)),
            self.logs.getvalue())

    @mock.patch("cloudinit.config.cc_ntp.ntp_installable")
    def test_ntp_handler_mocked_template(self, m_ntp_install):
        """Test ntp handler renders ubuntu ntp.conf template."""
        pools = ['0.mycompany.pool.ntp.org', '3.mycompany.pool.ntp.org']
        servers = ['192.168.23.3', '192.168.23.4']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers
            }
        }
        mycloud = self._get_cloud('ubuntu')
        ntp_conf = self.tmp_path('ntp.conf', self.new_root)  # Doesn't exist
        m_ntp_install.return_value = True

        # Create ntp.conf.tmpl
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            with mock.patch.object(util, 'which', return_value=None):
                cc_ntp.handle('notimportant', cfg, mycloud, None, None)

        content = util.read_file_or_url('file://' + ntp_conf).contents
        self.assertEqual(
            'servers {0}\npools {1}\n'.format(servers, pools),
            content.decode())

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_handler_mocked_template_snappy(self, m_util):
        """Test ntp handler renders timesycnd.conf template on snappy."""
        pools = ['0.mycompany.pool.ntp.org', '3.mycompany.pool.ntp.org']
        servers = ['192.168.23.3', '192.168.23.4']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers
            }
        }
        mycloud = self._get_cloud('ubuntu')
        m_util.system_is_snappy.return_value = True

        # Create timesyncd.conf.tmpl
        tsyncd_conf = self.tmp_path("timesyncd.conf", self.new_root)
        template = '{0}.tmpl'.format(tsyncd_conf)
        with open(template, 'wb') as stream:
            stream.write(TIMESYNCD_TEMPLATE)

        with mock.patch('cloudinit.config.cc_ntp.TIMESYNCD_CONF', tsyncd_conf):
            cc_ntp.handle('notimportant', cfg, mycloud, None, None)

        content = util.read_file_or_url('file://' + tsyncd_conf).contents
        self.assertEqual(
            "[Time]\nNTP=%s %s \n" % (" ".join(servers), " ".join(pools)),
            content.decode())

    def test_ntp_handler_real_distro_templates(self):
        """Test ntp handler renders the shipped distro ntp.conf templates."""
        pools = ['0.mycompany.pool.ntp.org', '3.mycompany.pool.ntp.org']
        servers = ['192.168.23.3', '192.168.23.4']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers
            }
        }
        ntp_conf = self.tmp_path('ntp.conf', self.new_root)  # Doesn't exist
        for distro in ('debian', 'ubuntu', 'fedora', 'rhel', 'sles'):
            mycloud = self._get_cloud(distro)
            root_dir = dirname(dirname(os.path.realpath(util.__file__)))
            tmpl_file = os.path.join(
                '{0}/templates/ntp.conf.{1}.tmpl'.format(root_dir, distro))
            # Create a copy in our tmp_dir
            shutil.copy(
                tmpl_file,
                os.path.join(self.new_root, 'ntp.conf.%s.tmpl' % distro))
            with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
                with mock.patch.object(util, 'which', return_value=[True]):
                    cc_ntp.handle('notimportant', cfg, mycloud, None, None)

            content = util.read_file_or_url('file://' + ntp_conf).contents
            expected_servers = '\n'.join([
                'server {0} iburst'.format(server) for server in servers])
            self.assertIn(
                expected_servers, content.decode(),
                'failed to render ntp.conf for distro:{0}'.format(distro))
            expected_pools = '\n'.join([
                'pool {0} iburst'.format(pool) for pool in pools])
            self.assertIn(
                expected_pools, content.decode(),
                'failed to render ntp.conf for distro:{0}'.format(distro))

    def test_no_ntpcfg_does_nothing(self):
        """When no ntp section is defined handler logs a warning and noops."""
        cc_ntp.handle('cc_ntp', {}, None, None, [])
        self.assertEqual(
            'DEBUG: Skipping module named cc_ntp, '
            'not present or disabled by cfg\n',
            self.logs.getvalue())

    def test_ntp_handler_schema_validation_allows_empty_ntp_config(self):
        """Ntp schema validation allows for an empty ntp: configuration."""
        valid_empty_configs = [{'ntp': {}}, {'ntp': None}]
        distro = 'ubuntu'
        cc = self._get_cloud(distro)
        ntp_conf = os.path.join(self.new_root, 'ntp.conf')
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        for valid_empty_config in valid_empty_configs:
            with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
                cc_ntp.handle('cc_ntp', valid_empty_config, cc, None, [])
            with open(ntp_conf) as stream:
                content = stream.read()
            default_pools = [
                "{0}.{1}.pool.ntp.org".format(x, distro)
                for x in range(0, cc_ntp.NR_POOL_SERVERS)]
            self.assertEqual(
                "servers []\npools {0}\n".format(default_pools),
                content)
        self.assertNotIn('Invalid config:', self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_ntp_handler_schema_validation_warns_non_string_item_type(self):
        """Ntp schema validation warns of non-strings in pools or servers.

        Schema validation is not strict, so ntp config is still be rendered.
        """
        invalid_config = {'ntp': {'pools': [123], 'servers': ['valid', None]}}
        cc = self._get_cloud('ubuntu')
        ntp_conf = os.path.join(self.new_root, 'ntp.conf')
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.handle('cc_ntp', invalid_config, cc, None, [])
        self.assertIn(
            "Invalid config:\nntp.pools.0: 123 is not of type 'string'\n"
            "ntp.servers.1: None is not of type 'string'",
            self.logs.getvalue())
        with open(ntp_conf) as stream:
            content = stream.read()
        self.assertEqual("servers ['valid', None]\npools [123]\n", content)

    @skipUnlessJsonSchema()
    def test_ntp_handler_schema_validation_warns_of_non_array_type(self):
        """Ntp schema validation warns of non-array pools or servers types.

        Schema validation is not strict, so ntp config is still be rendered.
        """
        invalid_config = {'ntp': {'pools': 123, 'servers': 'non-array'}}
        cc = self._get_cloud('ubuntu')
        ntp_conf = os.path.join(self.new_root, 'ntp.conf')
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.handle('cc_ntp', invalid_config, cc, None, [])
        self.assertIn(
            "Invalid config:\nntp.pools: 123 is not of type 'array'\n"
            "ntp.servers: 'non-array' is not of type 'array'",
            self.logs.getvalue())
        with open(ntp_conf) as stream:
            content = stream.read()
        self.assertEqual("servers non-array\npools 123\n", content)

    @skipUnlessJsonSchema()
    def test_ntp_handler_schema_validation_warns_invalid_key_present(self):
        """Ntp schema validation warns of invalid keys present in ntp config.

        Schema validation is not strict, so ntp config is still be rendered.
        """
        invalid_config = {
            'ntp': {'invalidkey': 1, 'pools': ['0.mycompany.pool.ntp.org']}}
        cc = self._get_cloud('ubuntu')
        ntp_conf = os.path.join(self.new_root, 'ntp.conf')
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.handle('cc_ntp', invalid_config, cc, None, [])
        self.assertIn(
            "Invalid config:\nntp: Additional properties are not allowed "
            "('invalidkey' was unexpected)",
            self.logs.getvalue())
        with open(ntp_conf) as stream:
            content = stream.read()
        self.assertEqual(
            "servers []\npools ['0.mycompany.pool.ntp.org']\n",
            content)

    @skipUnlessJsonSchema()
    def test_ntp_handler_schema_validation_warns_of_duplicates(self):
        """Ntp schema validation warns of duplicates in servers or pools.

        Schema validation is not strict, so ntp config is still be rendered.
        """
        invalid_config = {
            'ntp': {'pools': ['0.mypool.org', '0.mypool.org'],
                    'servers': ['10.0.0.1', '10.0.0.1']}}
        cc = self._get_cloud('ubuntu')
        ntp_conf = os.path.join(self.new_root, 'ntp.conf')
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.handle('cc_ntp', invalid_config, cc, None, [])
        self.assertIn(
            "Invalid config:\nntp.pools: ['0.mypool.org', '0.mypool.org'] has "
            "non-unique elements\nntp.servers: ['10.0.0.1', '10.0.0.1'] has "
            "non-unique elements",
            self.logs.getvalue())
        with open(ntp_conf) as stream:
            content = stream.read()
        self.assertEqual(
            "servers ['10.0.0.1', '10.0.0.1']\n"
            "pools ['0.mypool.org', '0.mypool.org']\n",
            content)

    @mock.patch("cloudinit.config.cc_ntp.ntp_installable")
    def test_ntp_handler_timesyncd(self, m_ntp_install):
        """Test ntp handler configures timesyncd"""
        m_ntp_install.return_value = False
        distro = 'ubuntu'
        cfg = {
            'servers': ['192.168.2.1', '192.168.2.2'],
            'pools': ['0.mypool.org'],
        }
        mycloud = self._get_cloud(distro)
        tsyncd_conf = self.tmp_path("timesyncd.conf", self.new_root)
        # Create timesyncd.conf.tmpl
        template = '{0}.tmpl'.format(tsyncd_conf)
        print(template)
        with open(template, 'wb') as stream:
            stream.write(TIMESYNCD_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.TIMESYNCD_CONF', tsyncd_conf):
            cc_ntp.write_ntp_config_template(cfg, mycloud, tsyncd_conf,
                                             template='timesyncd.conf')

        content = util.read_file_or_url('file://' + tsyncd_conf).contents
        self.assertEqual(
            "[Time]\nNTP=192.168.2.1 192.168.2.2 0.mypool.org \n",
            content.decode())

    def test_write_ntp_config_template_defaults_pools_empty_lists_sles(self):
        """write_ntp_config_template defaults pools servers upon empty config.

        When both pools and servers are empty, default NR_POOL_SERVERS get
        configured.
        """
        distro = 'sles'
        mycloud = self._get_cloud(distro)
        ntp_conf = self.tmp_path('ntp.conf', self.new_root)  # Doesn't exist
        # Create ntp.conf.tmpl
        with open('{0}.tmpl'.format(ntp_conf), 'wb') as stream:
            stream.write(NTP_TEMPLATE)
        with mock.patch('cloudinit.config.cc_ntp.NTP_CONF', ntp_conf):
            cc_ntp.write_ntp_config_template({}, mycloud, ntp_conf)
        content = util.read_file_or_url('file://' + ntp_conf).contents
        default_pools = [
            "{0}.opensuse.pool.ntp.org".format(x)
            for x in range(0, cc_ntp.NR_POOL_SERVERS)]
        self.assertEqual(
            "servers []\npools {0}\n".format(default_pools),
            content.decode())
        self.assertIn(
            "Adding distro default ntp pool servers: {0}".format(
                ",".join(default_pools)),
            self.logs.getvalue())


# vi: ts=4 expandtab
