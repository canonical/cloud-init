# This file is part of cloud-init. See LICENSE file for license information.

""" test_apk_configure
Test creation of repositories file
"""

import logging
import unittest
from contextlib import ExitStack
from unittest import mock

from cloudinit import cloud
from cloudinit import helpers
from cloudinit import util

from cloudinit.config import cc_apk_configure
from cloudinit.tests.helpers import TestCase


DEFAULT_MIRROR_URL = "https://alpine.global.ssl.fastly.net/alpine"

EXPECTED_COMMENT_HEADER = """
#
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


class TestNoConfig(unittest.TestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.name = "apk-configure"
        self.cloud_init = None
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    def test_no_config(self):
        """
        Test that nothing is done if no apk-configure
        configuration is provided.
        """
        config = util.get_builtin_cfg()
        with ExitStack() as mocks:
            util_mock = mocks.enter_context(
                mock.patch.object(util, 'write_file'))

            cc_apk_configure.handle(self.name, config, self.cloud_init,
                                    self.log, self.args)

            self.assertEqual(util_mock.call_count, 0)


class TestConfig(TestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "apk-configure"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

        self.mocks = ExitStack()
        self.addCleanup(self.mocks.close)

        # Mock out the functions that actually modify the system
        self.mock_writefile = self.mocks.enter_context(
            mock.patch.object(cc_apk_configure, 'write_repositories'))

    def test_no_repo_settings(self):
        """
        Test that nothing is written if the 'alpine-repo' key
        is not present.
        """
        config = {"apk_repos": {}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 0)

    def test_empty_repo_settings(self):
        """
        Test that nothing is written if 'alpine_repo' list is empty.
        """
        config = {"apk_repos": {"alpine_repos": []}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 0)

    def test_only_main_repo(self):
        """
        Test when only details of main repo is written to file.
        """
        alpine_version = 'v3.12'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        expected = EXPECTED_COMMENT_HEADER + main_repo + '\n'
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)

    def test_main_and_community_repos(self):
        """
        Test when only details of main and community repos are
        written to file.
        """
        alpine_version = 'edge'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version,
                    "community_enabled": true
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        expected = (EXPECTED_COMMENT_HEADER + main_repo +
                    community_repo + '\n')
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)

    def test_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        are written to file.
        """
        alpine_version = 'v3.12'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version,
                    "community_enabled": true
                    "testing_enabled": true
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                        '/testing\n')
        expected = (EXPECTED_COMMENT_HEADER + main_repo +
                    community_repo + EXPECTED_ALPINE_312_TESTING_COMMENT +
                    testing_repo + '\n')
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)

    def test_edge_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        for Edge version of Alpine are written to file.
        """
        alpine_version = 'edge'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version,
                    "community_enabled": true
                    "testing_enabled": true
                }
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/testing\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    testing_repo + '\n')
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)

    def test_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and
        local repos are written to file.
        """
        alpine_version = 'v3.12'
        local_repo_url = 'http://some.mirror/whereever'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version,
                    "community_enabled": true
                    "testing_enabled": true
                },
                "local_repo_base_url": local_repo_url
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/testing\n'
        local_repo = local_repo_url + '/' + alpine_version\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    EXPECTED_ALPINE_312_TESTING_COMMENT + testing_repo +
                    EXPECTED_LOCAL_REPO_COMMENT_HEADER + local_repo + '\n')
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)

    def test_edge_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and local repos
        for Edge version of Alpine are written to file.
        """
        alpine_version = 'edge'
        local_repo_url = 'http://some.mirror/whereever'
        config = {
            "apk_repos": {
                "alpine_repos": {
                    "version": alpine_version,
                    "community_enabled": true
                    "testing_enabled": true
                },
                "local_repo_base_url": local_repo_url
            }
        }

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(self.mock_writefile.call_count, 1)
        main_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/main\n'
        community_repo = (DEFAULT_MIRROR_URL + '/' + alpine_version +
                          '/community\n')
        testing_repo = DEFAULT_MIRROR_URL + '/' + alpine_version + '/testing\n'
        local_repo = local_repo_url + '/' + alpine_version\n'
        expected = (EXPECTED_COMMENT_HEADER + main_repo + community_repo +
                    testing_repo + EXPECTED_LOCAL_REPO_COMMENT_HEADER +
                    local_repo + '\n')
        self.assertEqual(util.load_file('/etc/apk/repositories'), expected)


# vi: ts=4 expandtab
