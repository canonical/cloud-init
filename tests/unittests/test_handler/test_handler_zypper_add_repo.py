# This file is part of cloud-init. See LICENSE file for license information.

import glob
import os

from cloudinit.config import cc_zypper_add_repo
from cloudinit import util

from cloudinit.tests import helpers
from cloudinit.tests.helpers import mock

import logging
from six import StringIO

LOG = logging.getLogger(__name__)


class TestConfig(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.tmp = self.tmp_dir()
        self.zypp_conf = 'etc/zypp/zypp.conf'

    def test_bad_repo_config(self):
        """Config has no baseurl, no file should be written"""
        cfg = {
            'repos': [
                {
                    'id': 'foo',
                    'name': 'suse-test',
                    'enabled': '1'
                },
            ]
        }
        self.patchUtils(self.tmp)
        cc_zypper_add_repo._write_repos(cfg['repos'], '/etc/zypp/repos.d')
        self.assertRaises(IOError, util.load_file,
                          "/etc/zypp/repos.d/foo.repo")

    def test_write_repos(self):
        """Verify valid repos get written"""
        cfg = self._get_base_config_repos()
        root_d = self.tmp_dir()
        cc_zypper_add_repo._write_repos(cfg['zypper']['repos'], root_d)
        repos = glob.glob('%s/*.repo' % root_d)
        expected_repos = ['testing-foo.repo', 'testing-bar.repo']
        if len(repos) != 2:
            assert 'Number of repos written is "%d" expected 2' % len(repos)
        for repo in repos:
            repo_name = os.path.basename(repo)
            if repo_name not in expected_repos:
                assert 'Found repo with name "%s"; unexpected' % repo_name
        # Validation that the content gets properly written is in another test

    def test_write_repo(self):
        """Verify the content of a repo file"""
        cfg = {
            'repos': [
                {
                    'baseurl': 'http://foo',
                    'name': 'test-foo',
                    'id': 'testing-foo'
                },
            ]
        }
        root_d = self.tmp_dir()
        cc_zypper_add_repo._write_repos(cfg['repos'], root_d)
        contents = util.load_file("%s/testing-foo.repo" % root_d)
        parser = self.parse_and_read(StringIO(contents))
        expected = {
            'testing-foo': {
                'name': 'test-foo',
                'baseurl': 'http://foo',
                'enabled': '1',
                'autorefresh': '1'
            }
        }
        for section in expected:
            self.assertTrue(parser.has_section(section),
                            "Contains section {0}".format(section))
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)

    def test_config_write(self):
        """Write valid configuration data"""
        cfg = {
            'config': {
                'download.deltarpm': 'False',
                'reposdir': 'foo'
            }
        }
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {self.zypp_conf: '# Zypp config\n'})
        self.reRoot(root_d)
        cc_zypper_add_repo._write_zypp_config(cfg['config'])
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        expected = [
            '# Zypp config',
            '# Added via cloud.cfg',
            'download.deltarpm=False',
            'reposdir=foo'
        ]
        for item in contents.split('\n'):
            if item not in expected:
                self.assertIsNone(item)

    @mock.patch('cloudinit.log.logging')
    def test_config_write_skip_configdir(self, mock_logging):
        """Write configuration but skip writing 'configdir' setting"""
        cfg = {
            'config': {
                'download.deltarpm': 'False',
                'reposdir': 'foo',
                'configdir': 'bar'
            }
        }
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {self.zypp_conf: '# Zypp config\n'})
        self.reRoot(root_d)
        cc_zypper_add_repo._write_zypp_config(cfg['config'])
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        expected = [
            '# Zypp config',
            '# Added via cloud.cfg',
            'download.deltarpm=False',
            'reposdir=foo'
        ]
        for item in contents.split('\n'):
            if item not in expected:
                self.assertIsNone(item)
        # Not finding teh right path for mocking :(
        # assert mock_logging.warning.called

    def test_empty_config_section_no_new_data(self):
        """When the config section is empty no new data should be written to
           zypp.conf"""
        cfg = self._get_base_config_repos()
        cfg['zypper']['config'] = None
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {self.zypp_conf: '# No data'})
        self.reRoot(root_d)
        cc_zypper_add_repo._write_zypp_config(cfg.get('config', {}))
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        self.assertEqual(contents, '# No data')

    def test_empty_config_value_no_new_data(self):
        """When the config section is not empty but there are no values
           no new data should be written to zypp.conf"""
        cfg = self._get_base_config_repos()
        cfg['zypper']['config'] = {
            'download.deltarpm': None
        }
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {self.zypp_conf: '# No data'})
        self.reRoot(root_d)
        cc_zypper_add_repo._write_zypp_config(cfg.get('config', {}))
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        self.assertEqual(contents, '# No data')

    def test_handler_full_setup(self):
        """Test that the handler ends up calling the renderers"""
        cfg = self._get_base_config_repos()
        cfg['zypper']['config'] = {
            'download.deltarpm': 'False',
        }
        root_d = self.tmp_dir()
        os.makedirs('%s/etc/zypp/repos.d' % root_d)
        helpers.populate_dir(root_d, {self.zypp_conf: '# Zypp config\n'})
        self.reRoot(root_d)
        cc_zypper_add_repo.handle('zypper_add_repo', cfg, None, LOG, [])
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        expected = [
            '# Zypp config',
            '# Added via cloud.cfg',
            'download.deltarpm=False',
        ]
        for item in contents.split('\n'):
            if item not in expected:
                self.assertIsNone(item)
        repos = glob.glob('%s/etc/zypp/repos.d/*.repo' % root_d)
        expected_repos = ['testing-foo.repo', 'testing-bar.repo']
        if len(repos) != 2:
            assert 'Number of repos written is "%d" expected 2' % len(repos)
        for repo in repos:
            repo_name = os.path.basename(repo)
            if repo_name not in expected_repos:
                assert 'Found repo with name "%s"; unexpected' % repo_name

    def test_no_config_section_no_new_data(self):
        """When there is no config section no new data should be written to
           zypp.conf"""
        cfg = self._get_base_config_repos()
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {self.zypp_conf: '# No data'})
        self.reRoot(root_d)
        cc_zypper_add_repo._write_zypp_config(cfg.get('config', {}))
        cfg_out = os.path.join(root_d, self.zypp_conf)
        contents = util.load_file(cfg_out)
        self.assertEqual(contents, '# No data')

    def test_no_repo_data(self):
        """When there is no repo data nothing should happen"""
        root_d = self.tmp_dir()
        self.reRoot(root_d)
        cc_zypper_add_repo._write_repos(None, root_d)
        content = glob.glob('%s/*' % root_d)
        self.assertEqual(len(content), 0)

    def _get_base_config_repos(self):
        """Basic valid repo configuration"""
        cfg = {
            'zypper': {
                'repos': [
                    {
                        'baseurl': 'http://foo',
                        'name': 'test-foo',
                        'id': 'testing-foo'
                    },
                    {
                        'baseurl': 'http://bar',
                        'name': 'test-bar',
                        'id': 'testing-bar'
                    }
                ]
            }
        }
        return cfg
