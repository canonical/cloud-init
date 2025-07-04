# This file is part of cloud-init. See LICENSE file for license information.

import configparser
import glob
import logging
import os

import pytest

from cloudinit import util
from cloudinit.config import cc_zypper_add_repo
from tests.unittests import helpers

LOG = logging.getLogger(__name__)


ZYPP_CONF = "etc/zypp/zypp.conf"


@pytest.mark.usefixtures("fake_filesystem")
class TestConfig:

    def test_bad_repo_config(self):
        """Config has no baseurl, no file should be written"""
        cfg = {
            "repos": [
                {"id": "foo", "name": "suse-test", "enabled": "1"},
            ]
        }
        cc_zypper_add_repo._write_repos(cfg["repos"], "/etc/zypp/repos.d")
        with pytest.raises(IOError):
            util.load_text_file("/etc/zypp/repos.d/foo.repo")

    def test_write_repos(self, tmp_path):
        """Verify valid repos get written"""
        cfg = self._get_base_config_repos()
        root_d = str(tmp_path)
        cc_zypper_add_repo._write_repos(cfg["zypper"]["repos"], root_d)
        repos = glob.glob("%s/*.repo" % root_d)
        expected_repos = ["testing-foo.repo", "testing-bar.repo"]
        if len(repos) != 2:
            assert 'Number of repos written is "%d" expected 2' % len(repos)
        for repo in repos:
            repo_name = os.path.basename(repo)
            if repo_name not in expected_repos:
                assert 'Found repo with name "%s"; unexpected' % repo_name
        # Validation that the content gets properly written is in another test

    def test_write_repo(self, tmp_path):
        """Verify the content of a repo file"""
        cfg = {
            "repos": [
                {
                    "baseurl": "http://foo",
                    "name": "test-foo",
                    "id": "testing-foo",
                },
            ]
        }
        root_d = str(tmp_path)
        cc_zypper_add_repo._write_repos(cfg["repos"], root_d)
        contents = util.load_text_file("%s/testing-foo.repo" % root_d)
        parser = configparser.ConfigParser()
        parser.read_string(contents)
        expected = {
            "testing-foo": {
                "name": "test-foo",
                "baseurl": "http://foo",
                "enabled": "1",
                "autorefresh": "1",
            }
        }
        for section in expected:
            assert parser.has_section(section), "Contains section {0}".format(
                section
            )
            for k, v in expected[section].items():
                assert parser.get(section, k) == v

    def test_config_write(self, tmp_path):
        """Write valid configuration data"""
        cfg = {"config": {"download.deltarpm": "False", "reposdir": "foo"}}
        root_d = str(tmp_path)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# Zypp config\n"})
        cc_zypper_add_repo._write_zypp_config(cfg["config"])
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        expected = [
            "# Zypp config",
            "# Added via cloud.cfg",
            "download.deltarpm=False",
            "reposdir=foo",
        ]
        for item in contents.split("\n"):
            if item not in expected:
                assert item is None

    def test_config_write_skip_configdir(self, tmp_path):
        """Write configuration but skip writing 'configdir' setting"""
        cfg = {
            "config": {
                "download.deltarpm": "False",
                "reposdir": "foo",
                "configdir": "bar",
            }
        }
        root_d = str(tmp_path)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# Zypp config\n"})
        cc_zypper_add_repo._write_zypp_config(cfg["config"])
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        expected = [
            "# Zypp config",
            "# Added via cloud.cfg",
            "download.deltarpm=False",
            "reposdir=foo",
        ]
        for item in contents.split("\n"):
            if item not in expected:
                assert item is None
        # Not finding teh right path for mocking :(
        # assert mock_logging.warning.called

    def test_empty_config_section_no_new_data(self, tmp_path):
        """When the config section is empty no new data should be written to
        zypp.conf"""
        cfg = self._get_base_config_repos()
        cfg["zypper"]["config"] = None
        root_d = str(tmp_path)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# No data"})
        cc_zypper_add_repo._write_zypp_config(cfg.get("config", {}))
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        assert contents == "# No data"

    def test_empty_config_value_no_new_data(self, tmp_path):
        """When the config section is not empty but there are no values
        no new data should be written to zypp.conf"""
        cfg = self._get_base_config_repos()
        cfg["zypper"]["config"] = {"download.deltarpm": None}
        root_d = str(tmp_path)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# No data"})
        cc_zypper_add_repo._write_zypp_config(cfg.get("config", {}))
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        assert contents == "# No data"

    def test_handler_full_setup(self, tmp_path):
        """Test that the handler ends up calling the renderers"""
        cfg = self._get_base_config_repos()
        cfg["zypper"]["config"] = {
            "download.deltarpm": "False",
        }
        root_d = str(tmp_path)
        os.makedirs("%s/etc/zypp/repos.d" % root_d)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# Zypp config\n"})
        cc_zypper_add_repo.handle("zypper_add_repo", cfg, None, [])
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        expected = [
            "# Zypp config",
            "# Added via cloud.cfg",
            "download.deltarpm=False",
        ]
        for item in contents.split("\n"):
            if item not in expected:
                assert item is None
        repos = glob.glob("%s/etc/zypp/repos.d/*.repo" % root_d)
        expected_repos = ["testing-foo.repo", "testing-bar.repo"]
        if len(repos) != 2:
            assert 'Number of repos written is "%d" expected 2' % len(repos)
        for repo in repos:
            repo_name = os.path.basename(repo)
            if repo_name not in expected_repos:
                assert 'Found repo with name "%s"; unexpected' % repo_name

    def test_no_config_section_no_new_data(self, tmp_path):
        """When there is no config section no new data should be written to
        zypp.conf"""
        cfg = self._get_base_config_repos()
        root_d = str(tmp_path)
        helpers.populate_dir(root_d, {ZYPP_CONF: "# No data"})
        cc_zypper_add_repo._write_zypp_config(cfg.get("config", {}))
        cfg_out = os.path.join(root_d, ZYPP_CONF)
        contents = util.load_text_file(cfg_out)
        assert contents == "# No data"

    def test_no_repo_data(self, tmp_path):
        """When there is no repo data nothing should happen"""
        # fake_filesystem creates a `tmp` dir a more under tmp_path
        root_d = str(tmp_path / "isolated")
        cc_zypper_add_repo._write_repos(None, root_d)
        content = glob.glob("%s/*" % root_d)
        assert len(content) == 0

    def _get_base_config_repos(self):
        """Basic valid repo configuration"""
        cfg = {
            "zypper": {
                "repos": [
                    {
                        "baseurl": "http://foo",
                        "name": "test-foo",
                        "id": "testing-foo",
                    },
                    {
                        "baseurl": "http://bar",
                        "name": "test-bar",
                        "id": "testing-bar",
                    },
                ]
            }
        }
        return cfg
