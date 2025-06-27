# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os
from pathlib import Path

from cloudinit import sources
from tests.helpers import cloud_init_project_dir, get_top_level_dir
from tests.unittests.helpers import get_mock_paths


class MyDataSource(sources.DataSource):
    _instance_id = None

    def get_instance_id(self):
        return self._instance_id


class TestPaths:
    def test_get_ipath_and_instance_id_with_slashes(self, tmp_path):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = "/foo/bar"
        safe_iid = "_foo_bar"
        mypaths = get_mock_paths(tmp_path)({}, myds)

        assert (
            os.path.join(mypaths.cloud_dir, "instances", safe_iid)
            == mypaths.get_ipath()
        )

    def test_get_ipath_and_empty_instance_id_returns_none(self, tmp_path):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = None
        mypaths = get_mock_paths(tmp_path)({}, myds)

        assert mypaths.get_ipath() is None


class Testcloud_init_project_dir:
    top_dir = get_top_level_dir()

    @staticmethod
    def _get_top_level_dir_alt_implementation():
        """Alternative implementation for comparing against.

        Note: Recursively searching for .git/ fails during build tests due to
        .git not existing. This implementation assumes that ../../../ is the
        relative path to the cloud-init project directory form this file.
        """
        out = Path(__file__).parent.parent.parent.resolve()
        return out

    def test_top_level_dir(self):
        """Assert the location of the top project directory is correct"""
        assert self.top_dir == self._get_top_level_dir_alt_implementation()

    def test_cloud_init_project_dir(self):
        """Assert cloud_init_project_dir produces an expected location

        Compare the returned value to an alternate (naive) implementation
        """
        assert (
            str(Path(self.top_dir, "test"))
            == cloud_init_project_dir("test")
            == str(Path(self._get_top_level_dir_alt_implementation(), "test"))
        )
