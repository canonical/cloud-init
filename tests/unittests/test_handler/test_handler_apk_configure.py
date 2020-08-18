# This file is part of cloud-init. See LICENSE file for license information.

""" test_apk_configure
Test creation of repositories file
"""

import logging
import os
import textwrap

from cloudinit import (cloud, helpers, util)

from cloudinit.config import cc_apk_configure
from cloudinit.tests.helpers import (FilesystemMockingTestCase, mock)

REPO_FILE = "/etc/apk/repositories"
DEFAULT_MIRROR_URL = "https://alpine.global.ssl.fastly.net/alpine"
CC_APK = 'cloudinit.config.cc_apk_configure'


class TestNoConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.add_patch(CC_APK + '._write_repositories_file', 'm_write_repos')
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

        cc_apk_configure.handle(self.name, config, self.cloud_init,
                                self.log, self.args)

        self.assertEqual(0, self.m_write_repos.call_count)


class TestConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.new_root = self.tmp_dir()
        self.new_root = self.reRoot(root=self.new_root)
        for dirname in ['tmp', 'etc/apk']:
            util.ensure_dir(os.path.join(self.new_root, dirname))
        self.paths = helpers.Paths({'templates_dir': self.new_root})
        self.name = "apk-configure"
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestNoConfig")
        self.args = []

    @mock.patch(CC_APK + '._write_repositories_file')
    def test_no_repo_settings(self, m_write_repos):
        """
        Test that nothing is written if the 'alpine-repo' key
        is not present.
        """
        config = {"apk_repos": {}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(0, m_write_repos.call_count)

    @mock.patch(CC_APK + '._write_repositories_file')
    def test_empty_repo_settings(self, m_write_repos):
        """
        Test that nothing is written if 'alpine_repo' list is empty.
        """
        config = {"apk_repos": {"alpine_repo": []}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertEqual(0, m_write_repos.call_count)

    def test_only_main_repo(self):
        """
        Test when only details of main repo is written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main

            """.format(DEFAULT_MIRROR_URL, alpine_version))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))

    def test_main_and_community_repos(self):
        """
        Test when only details of main and community repos are
        written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community

            """.format(DEFAULT_MIRROR_URL, alpine_version))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))

    def test_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        are written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            #
            # Testing - using with non-Edge installation may cause problems!
            #
            {0}/edge/testing

            """.format(DEFAULT_MIRROR_URL, alpine_version))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))

    def test_edge_main_community_testing_repos(self):
        """
        Test when details of main, community and testing repos
        for Edge version of Alpine are written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            {0}/{1}/testing

            """.format(DEFAULT_MIRROR_URL, alpine_version))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))

    def test_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and
        local repos are written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            #
            # Testing - using with non-Edge installation may cause problems!
            #
            {0}/edge/testing

            #
            # Local repo
            #
            {2}/{1}

            """.format(DEFAULT_MIRROR_URL, alpine_version, local_repo_url))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))

    def test_edge_main_community_testing_local_repos(self):
        """
        Test when details of main, community, testing and local repos
        for Edge version of Alpine are written to file.
        """
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

        expected_content = textwrap.dedent("""\
            #
            # Created by cloud-init
            #
            # This file is written on first boot of an instance
            #

            {0}/{1}/main
            {0}/{1}/community
            {0}/edge/testing

            #
            # Local repo
            #
            {2}/{1}

            """.format(DEFAULT_MIRROR_URL, alpine_version, local_repo_url))

        self.assertEqual(expected_content, util.load_file(REPO_FILE))


# vi: ts=4 expandtab
