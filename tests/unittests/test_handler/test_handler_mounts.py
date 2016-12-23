# This file is part of cloud-init. See LICENSE file for license information.

import os.path
import shutil
import tempfile

from cloudinit.config import cc_mounts

from .. import helpers as test_helpers

try:
    from unittest import mock
except ImportError:
    import mock


class TestSanitizeDevname(test_helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestSanitizeDevname, self).setUp()
        self.new_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.new_root)
        self.patchOS(self.new_root)

    def _touch(self, path):
        path = os.path.join(self.new_root, path.lstrip('/'))
        basedir = os.path.dirname(path)
        if not os.path.exists(basedir):
            os.makedirs(basedir)
        open(path, 'a').close()

    def _makedirs(self, directory):
        directory = os.path.join(self.new_root, directory.lstrip('/'))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def mock_existence_of_disk(self, disk_path):
        self._touch(disk_path)
        self._makedirs(os.path.join('/sys/block', disk_path.split('/')[-1]))

    def mock_existence_of_partition(self, disk_path, partition_number):
        self.mock_existence_of_disk(disk_path)
        self._touch(disk_path + str(partition_number))
        disk_name = disk_path.split('/')[-1]
        self._makedirs(os.path.join('/sys/block',
                                    disk_name,
                                    disk_name + str(partition_number)))

    def test_existent_full_disk_path_is_returned(self):
        disk_path = '/dev/sda'
        self.mock_existence_of_disk(disk_path)
        self.assertEqual(disk_path,
                         cc_mounts.sanitize_devname(disk_path,
                                                    lambda x: None,
                                                    mock.Mock()))

    def test_existent_disk_name_returns_full_path(self):
        disk_name = 'sda'
        disk_path = '/dev/' + disk_name
        self.mock_existence_of_disk(disk_path)
        self.assertEqual(disk_path,
                         cc_mounts.sanitize_devname(disk_name,
                                                    lambda x: None,
                                                    mock.Mock()))

    def test_existent_meta_disk_is_returned(self):
        actual_disk_path = '/dev/sda'
        self.mock_existence_of_disk(actual_disk_path)
        self.assertEqual(
            actual_disk_path,
            cc_mounts.sanitize_devname('ephemeral0',
                                       lambda x: actual_disk_path,
                                       mock.Mock()))

    def test_existent_meta_partition_is_returned(self):
        disk_name, partition_part = '/dev/sda', '1'
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(disk_name, partition_part)
        self.assertEqual(
            actual_partition_path,
            cc_mounts.sanitize_devname('ephemeral0.1',
                                       lambda x: disk_name,
                                       mock.Mock()))

    def test_existent_meta_partition_with_p_is_returned(self):
        disk_name, partition_part = '/dev/sda', 'p1'
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(disk_name, partition_part)
        self.assertEqual(
            actual_partition_path,
            cc_mounts.sanitize_devname('ephemeral0.1',
                                       lambda x: disk_name,
                                       mock.Mock()))

    def test_first_partition_returned_if_existent_disk_is_partitioned(self):
        disk_name, partition_part = '/dev/sda', '1'
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(disk_name, partition_part)
        self.assertEqual(
            actual_partition_path,
            cc_mounts.sanitize_devname('ephemeral0',
                                       lambda x: disk_name,
                                       mock.Mock()))

    def test_nth_partition_returned_if_requested(self):
        disk_name, partition_part = '/dev/sda', '3'
        actual_partition_path = disk_name + partition_part
        self.mock_existence_of_partition(disk_name, partition_part)
        self.assertEqual(
            actual_partition_path,
            cc_mounts.sanitize_devname('ephemeral0.3',
                                       lambda x: disk_name,
                                       mock.Mock()))

    def test_transformer_returning_none_returns_none(self):
        self.assertIsNone(
            cc_mounts.sanitize_devname(
                'ephemeral0', lambda x: None, mock.Mock()))

    def test_missing_device_returns_none(self):
        self.assertIsNone(
            cc_mounts.sanitize_devname('/dev/sda', None, mock.Mock()))

    def test_missing_sys_returns_none(self):
        disk_path = '/dev/sda'
        self._makedirs(disk_path)
        self.assertIsNone(
            cc_mounts.sanitize_devname(disk_path, None, mock.Mock()))

    def test_existent_disk_but_missing_partition_returns_none(self):
        disk_path = '/dev/sda'
        self.mock_existence_of_disk(disk_path)
        self.assertIsNone(
            cc_mounts.sanitize_devname(
                'ephemeral0.1', lambda x: disk_path, mock.Mock()))

# vi: ts=4 expandtab
