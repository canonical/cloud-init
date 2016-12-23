# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_ntp
from cloudinit.sources import DataSourceNone
from cloudinit import templater
from cloudinit import (distros, helpers, cloud, util)
from ..helpers import FilesystemMockingTestCase, mock

import logging
import os
import shutil
import tempfile

LOG = logging.getLogger(__name__)

NTP_TEMPLATE = """
## template: jinja

{% if pools %}# pools
{% endif %}
{% for pool in pools -%}
pool {{pool}} iburst
{% endfor %}
{%- if servers %}# servers
{% endif %}
{% for server in servers -%}
server {{server}} iburst
{% endfor %}

"""


NTP_EXPECTED_UBUNTU = """
# pools
pool 0.mycompany.pool.ntp.org iburst
# servers
server 192.168.23.3 iburst

"""


class TestNtp(FilesystemMockingTestCase):

    def setUp(self):
        super(TestNtp, self).setUp()
        self.subp = util.subp
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)

    def _get_cloud(self, distro, metadata=None):
        self.patchUtils(self.new_root)
        paths = helpers.Paths({})
        cls = distros.fetch(distro)
        mydist = cls(distro, {}, paths)
        myds = DataSourceNone.DataSourceNone({}, mydist, paths)
        if metadata:
            myds.metadata.update(metadata)
        return cloud.Cloud(myds, paths, {}, mydist, None)

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_install(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = None
        install_func = mock.MagicMock()

        cc_ntp.install_ntp(install_func, packages=['ntpx'], check_exe='ntpdx')

        self.assertTrue(install_func.called)
        mock_util.which.assert_called_with('ntpdx')
        install_pkg = install_func.call_args_list[0][0][0]
        self.assertEqual(sorted(install_pkg), ['ntpx'])

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_ntp_install_not_needed(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc.distro.name = 'ubuntu'
        mock_util.which.return_value = ["/usr/sbin/ntpd"]
        cc_ntp.install_ntp(cc)
        self.assertFalse(cc.distro.install_packages.called)

    def test_ntp_rename_ntp_conf(self):
        with mock.patch.object(os.path, 'exists',
                               return_value=True) as mockpath:
            with mock.patch.object(util, 'rename') as mockrename:
                cc_ntp.rename_ntp_conf()

        mockpath.assert_called_with('/etc/ntp.conf')
        mockrename.assert_called_with('/etc/ntp.conf', '/etc/ntp.conf.dist')

    def test_ntp_rename_ntp_conf_skip_missing(self):
        with mock.patch.object(os.path, 'exists',
                               return_value=False) as mockpath:
            with mock.patch.object(util, 'rename') as mockrename:
                cc_ntp.rename_ntp_conf()

        mockpath.assert_called_with('/etc/ntp.conf')
        mockrename.assert_not_called()

    def ntp_conf_render(self, distro):
        """ntp_conf_render
        Test rendering of a ntp.conf from template for a given distro
        """

        cfg = {'ntp': {}}
        mycloud = self._get_cloud(distro)
        distro_names = cc_ntp.generate_server_names(distro)

        with mock.patch.object(templater, 'render_to_file') as mocktmpl:
            with mock.patch.object(os.path, 'isfile', return_value=True):
                with mock.patch.object(util, 'rename'):
                    cc_ntp.write_ntp_config_template(cfg, mycloud)

        mocktmpl.assert_called_once_with(
            ('/etc/cloud/templates/ntp.conf.%s.tmpl' % distro),
            '/etc/ntp.conf',
            {'servers': [], 'pools': distro_names})

    def test_ntp_conf_render_rhel(self):
        """Test templater.render_to_file() for rhel"""
        self.ntp_conf_render('rhel')

    def test_ntp_conf_render_debian(self):
        """Test templater.render_to_file() for debian"""
        self.ntp_conf_render('debian')

    def test_ntp_conf_render_fedora(self):
        """Test templater.render_to_file() for fedora"""
        self.ntp_conf_render('fedora')

    def test_ntp_conf_render_sles(self):
        """Test templater.render_to_file() for sles"""
        self.ntp_conf_render('sles')

    def test_ntp_conf_render_ubuntu(self):
        """Test templater.render_to_file() for ubuntu"""
        self.ntp_conf_render('ubuntu')

    def test_ntp_conf_servers_no_pools(self):
        distro = 'ubuntu'
        pools = []
        servers = ['192.168.2.1']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers,
            }
        }
        mycloud = self._get_cloud(distro)

        with mock.patch.object(templater, 'render_to_file') as mocktmpl:
            with mock.patch.object(os.path, 'isfile', return_value=True):
                with mock.patch.object(util, 'rename'):
                    cc_ntp.write_ntp_config_template(cfg.get('ntp'), mycloud)

        mocktmpl.assert_called_once_with(
            ('/etc/cloud/templates/ntp.conf.%s.tmpl' % distro),
            '/etc/ntp.conf',
            {'servers': servers, 'pools': pools})

    def test_ntp_conf_custom_pools_no_server(self):
        distro = 'ubuntu'
        pools = ['0.mycompany.pool.ntp.org']
        servers = []
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers,
            }
        }
        mycloud = self._get_cloud(distro)

        with mock.patch.object(templater, 'render_to_file') as mocktmpl:
            with mock.patch.object(os.path, 'isfile', return_value=True):
                with mock.patch.object(util, 'rename'):
                    cc_ntp.write_ntp_config_template(cfg.get('ntp'), mycloud)

        mocktmpl.assert_called_once_with(
            ('/etc/cloud/templates/ntp.conf.%s.tmpl' % distro),
            '/etc/ntp.conf',
            {'servers': servers, 'pools': pools})

    def test_ntp_conf_custom_pools_and_server(self):
        distro = 'ubuntu'
        pools = ['0.mycompany.pool.ntp.org']
        servers = ['192.168.23.3']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers,
            }
        }
        mycloud = self._get_cloud(distro)

        with mock.patch.object(templater, 'render_to_file') as mocktmpl:
            with mock.patch.object(os.path, 'isfile', return_value=True):
                with mock.patch.object(util, 'rename'):
                    cc_ntp.write_ntp_config_template(cfg.get('ntp'), mycloud)

        mocktmpl.assert_called_once_with(
            ('/etc/cloud/templates/ntp.conf.%s.tmpl' % distro),
            '/etc/ntp.conf',
            {'servers': servers, 'pools': pools})

    def test_ntp_conf_contents_match(self):
        """Test rendered contents of /etc/ntp.conf for ubuntu"""
        pools = ['0.mycompany.pool.ntp.org']
        servers = ['192.168.23.3']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers,
            }
        }
        mycloud = self._get_cloud('ubuntu')
        side_effect = [NTP_TEMPLATE.lstrip()]

        # work backwards from util.write_file and mock out call path
        # write_ntp_config_template()
        #   cloud.get_template_filename()
        #     os.path.isfile()
        #   templater.render_to_file()
        #     templater.render_from_file()
        #         util.load_file()
        #     util.write_file()
        #
        with mock.patch.object(util, 'write_file') as mockwrite:
            with mock.patch.object(util, 'load_file', side_effect=side_effect):
                with mock.patch.object(os.path, 'isfile', return_value=True):
                    with mock.patch.object(util, 'rename'):
                        cc_ntp.write_ntp_config_template(cfg.get('ntp'),
                                                         mycloud)

        mockwrite.assert_called_once_with(
            '/etc/ntp.conf',
            NTP_EXPECTED_UBUNTU,
            mode=420)

    def test_ntp_handler(self):
        """Test ntp handler renders ubuntu ntp.conf template"""
        pools = ['0.mycompany.pool.ntp.org']
        servers = ['192.168.23.3']
        cfg = {
            'ntp': {
                'pools': pools,
                'servers': servers,
            }
        }
        mycloud = self._get_cloud('ubuntu')
        side_effect = [NTP_TEMPLATE.lstrip()]

        with mock.patch.object(util, 'which', return_value=None):
            with mock.patch.object(os.path, 'exists'):
                with mock.patch.object(util, 'write_file') as mockwrite:
                    with mock.patch.object(util, 'load_file',
                                           side_effect=side_effect):
                        with mock.patch.object(os.path, 'isfile',
                                               return_value=True):
                            with mock.patch.object(util, 'rename'):
                                cc_ntp.handle("notimportant", cfg,
                                              mycloud, LOG, None)

        mockwrite.assert_called_once_with(
            '/etc/ntp.conf',
            NTP_EXPECTED_UBUNTU,
            mode=420)

    @mock.patch("cloudinit.config.cc_ntp.util")
    def test_no_ntpcfg_does_nothing(self, mock_util):
        cc = self._get_cloud('ubuntu')
        cc.distro = mock.MagicMock()
        cc_ntp.handle('cc_ntp', {}, cc, LOG, [])
        self.assertFalse(cc.distro.install_packages.called)
        self.assertFalse(mock_util.subp.called)

# vi: ts=4 expandtab
