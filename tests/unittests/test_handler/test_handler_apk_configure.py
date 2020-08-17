# This file is part of cloud-init. See LICENSE file for license information.

""" test_apk_configure
Test creation of repositories file
"""

import logging
import os

from cloudinit import cloud
from cloudinit import temp_utils
from cloudinit import templater
from cloudinit import util

from cloudinit.config import cc_apk_configure
from cloudinit.tests.helpers import FilesystemMockingTestCase


REPO_FILE = "/etc/apk/repositories"
DEFAULT_MIRROR_URL = "https://alpine.global.ssl.fastly.net/alpine"

REPOSITORIES_TEMPLATE = """\
## template:jinja
#
# Created by cloud-init
#
# This file is written on first boot of an instance
#

{{ alpine_baseurl }}/{{ alpine_version }}/main
{% if community_enabled -%}
{{ alpine_baseurl }}/{{ alpine_version }}/community
{% endif -%}
{% if testing_enabled -%}
{% if alpine_version != 'edge' %}
#
# Testing - using this with a non-Edge installation will likely cause problems!
#
{% endif %}
{{ alpine_baseurl }}/edge/testing
{% endif %}
{% if local_repo != '' %}

#
# Local repo
#
{{ local_repo }}/{{ alpine_version }}
{% endif %}

"""


class TestNoConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestNoConfig, self).setUp()
        self.new_root = self.tmp_dir()
        util.ensure_dir(os.path.join(self.new_root, 'etc/apk'))
        self.new_root = self.reRoot(root=self.new_root)
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

        self.assertRaises(IOError, util.load_file, REPO_FILE)


class TestConfig(FilesystemMockingTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.new_root = self.tmp_dir()
        util.ensure_dir(os.path.join(self.new_root, 'etc/apk'))
        self.new_root = self.reRoot(root=self.new_root)
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
        config = {"apk_repos": {}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertRaises(IOError, util.load_file, REPO_FILE)

    def test_empty_repo_settings(self):
        """
        Test that nothing is written if 'alpine_repo' list is empty.
        """
        config = {"apk_repos": {"alpine_repo": []}}

        cc_apk_configure.handle(self.name, config, self.cloud, self.log,
                                self.args)

        self.assertRaises(IOError, util.load_file, REPO_FILE)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'local_repo': ''}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'community_enabled': True,
                  'local_repo': ''}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'community_enabled': True,
                  'testing_enabled': True,
                  'local_repo': ''}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'community_enabled': True,
                  'testing_enabled': True,
                  'local_repo': ''}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'community_enabled': True,
                  'testing_enabled': True,
                  'local_repo': local_repo_url}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)

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

        params = {'alpine_baseurl': DEFAULT_MIRROR_URL,
                  'alpine_version': alpine_version,
                  'community_enabled': True,
                  'testing_enabled': True,
                  'local_repo': local_repo_url}

        tfile = temp_utils.mkstemp(prefix='template_name-', suffix=".tmpl")
        template_fn = tfile[1]  # Filepath is second item in tuple
        util.write_file(template_fn, content=REPOSITORIES_TEMPLATE)

        expected_file = temp_utils.mkstemp(prefix='repositories-')
        expected_fn = expected_file[1]  # Filepath is second item in tuple
        templater.render_to_file(template_fn, expected_fn, params)

        self.assertEqual(util.load_file(REPO_FILE),
                         util.load_file(expected_fn))

        util.del_file(template_fn)
        util.del_file(expected_fn)


# vi: ts=4 expandtab
