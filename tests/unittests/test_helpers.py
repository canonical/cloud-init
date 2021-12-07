# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os
from os.path import abspath
from pathlib import Path

from tests.unittests import helpers as test_helpers

from cloudinit import sources


class MyDataSource(sources.DataSource):
    _instance_id = None

    def get_instance_id(self):
        return self._instance_id


class TestPaths(test_helpers.ResourceUsingTestCase):
    def test_get_ipath_and_instance_id_with_slashes(self):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = "/foo/bar"
        safe_iid = "_foo_bar"
        mypaths = self.getCloudPaths(myds)

        self.assertEqual(
            os.path.join(mypaths.cloud_dir, 'instances', safe_iid),
            mypaths.get_ipath())

    def test_get_ipath_and_empty_instance_id_returns_none(self):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = None
        mypaths = self.getCloudPaths(myds)

        self.assertIsNone(mypaths.get_ipath())


def cmp_abspath(*args):
    """Ensure arguments have the same abspath"""
    return 1 == len(set(map(abspath, map(str, args))))


class TestCloudinitDir:

    @staticmethod
    def _get_top_level_dir_alt_implementation():
        """Recursively walk until .git/ is found, return parent dir"""

        def get_git_dir(path):
            if os.path.isdir(str(Path(path, ".git"))):
                return Path(path, ".git").parent
            # found root dir, not going to find a .git/
            elif cmp_abspath('/', path):
                return False

            return get_git_dir(path / "..")

        return get_git_dir(Path("."))

    def test_top_level_dir(self):
        assert cmp_abspath(
            test_helpers.get_top_level_dir(),
            self._get_top_level_dir_alt_implementation(),
        )

# vi: ts=4 expandtab
