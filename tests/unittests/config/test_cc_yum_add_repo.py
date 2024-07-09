# This file is part of cloud-init. See LICENSE file for license information.

import configparser
import logging
import re
import shutil
import tempfile

import pytest

from cloudinit import util
from cloudinit.config import cc_yum_add_repo
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests import helpers

LOG = logging.getLogger(__name__)


class TestConfig(helpers.FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_bad_config(self):
        cfg = {
            "yum_repos": {
                "epel-testing": {
                    "name": "Extra Packages for Enterprise Linux 5 - Testing",
                    # At least one of baseurl or metalink must be present.
                    # Missing this should cause the repo not to be written
                    # 'baseurl': 'http://blah.org/pub/epel/testing/5/$barch',
                    "enabled": False,
                    "gpgcheck": True,
                    "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL",
                    "failovermethod": "priority",
                },
            },
        }
        self.patchUtils(self.tmp)
        cc_yum_add_repo.handle("yum_add_repo", cfg, None, [])
        self.assertRaises(
            IOError, util.load_text_file, "/etc/yum.repos.d/epel_testing.repo"
        )

    def test_metalink_config(self):
        cfg = {
            "yum_repos": {
                "epel-testing": {
                    "name": "Extra Packages for Enterprise Linux 5 - Testing",
                    "metalink": "http://blah.org/pub/epel/testing/5/$basearch",
                    "enabled": False,
                    "gpgcheck": True,
                    "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL",
                    "failovermethod": "priority",
                },
            },
        }
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)
        cc_yum_add_repo.handle("yum_add_repo", cfg, None, [])
        contents = util.load_text_file("/etc/yum.repos.d/epel-testing.repo")
        parser = configparser.ConfigParser()
        parser.read_string(contents)
        expected = {
            "epel-testing": {
                "name": "Extra Packages for Enterprise Linux 5 - Testing",
                "failovermethod": "priority",
                "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL",
                "enabled": "0",
                "metalink": "http://blah.org/pub/epel/testing/5/$basearch",
                "gpgcheck": "1",
            }
        }
        for section in expected:
            self.assertTrue(
                parser.has_section(section),
                "Contains section {0}".format(section),
            )
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)

    def test_write_config(self):
        cfg = {
            "yum_repos": {
                "epel-testing": {
                    "name": "Extra Packages for Enterprise Linux 5 - Testing",
                    "baseurl": "http://blah.org/pub/epel/testing/5/$basearch",
                    "enabled": False,
                    "gpgcheck": True,
                    "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL",
                    "failovermethod": "priority",
                },
            },
        }
        self.patchUtils(self.tmp)
        self.patchOS(self.tmp)
        cc_yum_add_repo.handle("yum_add_repo", cfg, None, [])
        contents = util.load_text_file("/etc/yum.repos.d/epel-testing.repo")
        parser = configparser.ConfigParser()
        parser.read_string(contents)
        expected = {
            "epel-testing": {
                "name": "Extra Packages for Enterprise Linux 5 - Testing",
                "failovermethod": "priority",
                "gpgkey": "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL",
                "enabled": "0",
                "baseurl": "http://blah.org/pub/epel/testing/5/$basearch",
                "gpgcheck": "1",
            }
        }
        for section in expected:
            self.assertTrue(
                parser.has_section(section),
                "Contains section {0}".format(section),
            )
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)

    def test_write_config_array(self):
        cfg = {
            "yum_repos": {
                "puppetlabs-products": {
                    "name": "Puppet Labs Products El 6 - $basearch",
                    "baseurl": (
                        "http://yum.puppetlabs.com/el/6/products/$basearch"
                    ),
                    "gpgkey": [
                        "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppetlabs",
                        "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppet",
                    ],
                    "enabled": True,
                    "gpgcheck": True,
                }
            }
        }
        self.patchUtils(self.tmp)
        cc_yum_add_repo.handle("yum_add_repo", cfg, None, [])
        contents = util.load_text_file(
            "/etc/yum.repos.d/puppetlabs-products.repo"
        )
        parser = configparser.ConfigParser()
        parser.read_string(contents)
        expected = {
            "puppetlabs-products": {
                "name": "Puppet Labs Products El 6 - $basearch",
                "baseurl": "http://yum.puppetlabs.com/el/6/products/$basearch",
                "gpgkey": (
                    "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppetlabs\n"
                    "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-puppet"
                ),
                "enabled": "1",
                "gpgcheck": "1",
            }
        }
        for section in expected:
            self.assertTrue(
                parser.has_section(section),
                "Contains section {0}".format(section),
            )
            for k, v in expected[section].items():
                self.assertEqual(parser.get(section, k), v)


class TestAddYumRepoSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Happy path case
            ({"yum_repos": {"My-Repo 123": {"baseurl": "http://doit"}}}, None),
            # yum_repo_dir is a string
            (
                {"yum_repo_dir": True},
                "yum_repo_dir: True is not of type 'string'",
            ),
            (
                {"yum_repos": {}},
                re.escape("yum_repos: {} ") + helpers.SCHEMA_EMPTY_ERROR,
            ),
            # baseurl required
            (
                {"yum_repos": {"My-Repo": {}}},
                "yum_repos.My-Repo: 'baseurl' is a required",
            ),
            # patternProperties don't override type of explicit property names
            (
                {"yum_repos": {"My Repo": {"enabled": "nope"}}},
                "yum_repos.My Repo.enabled: 'nope' is not of type 'boolean'",
            ),
            (
                {
                    "yum_repos": {
                        "hotwheels repo": {"": "config option requires a name"}
                    }
                },
                "does not match any of the regexes",
            ),
            (
                {
                    "yum_repos": {
                        "matchbox repo": {
                            "$$$$$": "config option requires a valid name"
                        }
                    }
                },
                "does not match any of the regexes",
            ),
        ],
    )
    @helpers.skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)
