# This file is part of cloud-init. See LICENSE file for license information.

""" test_apk_configure
Test creation of repositories file
"""

import logging
import os

from cloudinit import cloud
from cloudinit import util

from cloudinit.config import cc_apk_configure
from cloudinit.tests.helpers import FilesystemMockingTestCase


REPO_FILE = "/etc/apk/repositories"
DEFAULT_MIRROR_URL = "https://alpine.global.ssl.fastly.net/alpine"

EXPECTED_COMMENT_HEADER = """#
# Created by cloud-init
#
# This file is written on first boot of an instance
#

"""

EXPECTED_ALPINE_312_TESTING_COMMENT = """
#
# Testing - using this with a non-Edge installation will likely cause problems!
#
"""

EXPECTED_LOCAL_REPO_COMMENT_HEADER = """
#
# Local repo
#
"""


class TestNoConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.new_root = self.tmp_dir()
        util.ensure_dir(os.path.join(self.new_root, 'etc/apk'))
        self.name = "apk-configure"
        self.cloud_init = None
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    def test_no_config(self):
        """
        Test that nothing is done if no apk-configure
        configuration is provided.
        """
        self.new_root = self.reRoot(root=self.new_root)
        config = util.get_builtin_cfg()

        cc_apk_configure.handle(self.name, config, self.cloud_init,
                                self.log, self.args)

        self.assertRaises(IOError, util.load_file, REPO_FILE)


class TestConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.new_root = self.tmp_dir()
        util.ensure_dir(os.path.join(self.new_root, 'etc/apk'))
        self.name = "apk-configure"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    def test_no_repo_settings(self):
        """
        Test that nothing is written if the 'alpine-repo' key
        is not present.
        """
        self.new_root = self.reRoot(root=self.new_root)
        config = {"apk_repos": {}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertRaises(IOError, util.load_file, REPO_FILE)

    def test_empty_repo_settings(self):
        """
        Test that nothing is written if 'alpine_repo' list is empty.
        """
        self.new_root = self.reRoot(root=self.new_root)
        config = {"apk_repos": {"alpine_repo": []}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertRaises(IOError, util.load_file, REPO_FILE)

    def test_only_main_repo(self):
        """
        Test when only details of main repo is written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'v3.12'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        expected = EXPECTED_COMMENT_HEADER + main_repo + '\n'
        self.assertEqual(util.load_file(REPO_FILE), expected)

    def test_main_and_community_repos(self):
        """
        Test when only details of main and community repos are
        written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'edge'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        expected = (EXPECTED_COMMENT_HEADER + main_repo +
                    community_repo + '\n')
        self.assertEqual(util.load_file(REPO_FILE), expected)

    def test_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        are written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'v3.12'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/edge/testing\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo +
                    community_repo + EXPECTED_ALPINE_312_TESTING_COMMENT +
                    testing_repo + '\n')
        self.assertEqual(util.load_file(REPO_FILE), expected)

    def test_edge_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        for Edge version of Alpine are written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'edge'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/edge/testing\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    testing_repo + '\n')
        self.assertEqual(util.load_file(REPO_FILE), expected)

    def test_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and
        local repos are written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'v3.12'
        local_repo_url = 'http://some.mirror/whereever'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True
                },
                "local_repo_base_url": local_repo_url
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/edge/testing\n'
        local_repo = local_repo_url + '/' + alpine_version + '\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    EXPECTED_ALPINE_312_TESTING_COMMENT + testing_repo +
                    EXPECTED_LOCAL_REPO_COMMENT_HEADER + local_repo + '\n')
        self.assertEqual(util.load_file(REPO_FILE), expected)

    def test_edge_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and local repos
        for Edge version of Alpine are written to file.
        """
        self.new_root = self.reRoot(root=self.new_root)
        alpine_version = 'edge'
        local_repo_url = 'http://some.mirror/whereever'
        config = {
            "apk_repos": {
                "alpine_repo": {
                    "version": alpine_version,
                    "community_enabled": True,
                    "testing_enabled": True
                },
                "local_repo_base_url": local_repo_url
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/edge/testing\n'
        local_repo = local_repo_url + '/' + alpine_version + '\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    testing_repo + EXPECTED_LOCAL_REPO_COMMENT_HEADER +
                    local_repo + '\n')
        self.assertEqual(util.load_file(REPO_FILE), expected)


# vi: ts=4 expandtab
