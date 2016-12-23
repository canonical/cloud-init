# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os

from . import helpers as test_helpers

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

        self.assertEqual(None, mypaths.get_ipath())

# vi: ts=4 expandtab
