# This file is part of cloud-init. See LICENSE file for license information.

import random

from cloudinit.config import cc_disk_setup
from ..helpers import ExitStack, mock, TestCase


class TestIsDiskUsed(TestCase):

    def setUp(self):
        super(TestIsDiskUsed, self).setUp()
        self.patches = ExitStack()
        mod_name = 'cloudinit.config.cc_disk_setup'
        self.enumerate_disk = self.patches.enter_context(
            mock.patch('{0}.enumerate_disk'.format(mod_name)))
        self.check_fs = self.patches.enter_context(
            mock.patch('{0}.check_fs'.format(mod_name)))

    def test_multiple_child_nodes_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(2))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        self.assertTrue(cc_disk_setup.is_disk_used(mock.MagicMock()))

    def test_valid_filesystem_returns_true(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (
            mock.MagicMock(), 'ext4', mock.MagicMock())
        self.assertTrue(cc_disk_setup.is_disk_used(mock.MagicMock()))

    def test_one_child_nodes_and_no_fs_returns_false(self):
        self.enumerate_disk.return_value = (mock.MagicMock() for _ in range(1))
        self.check_fs.return_value = (mock.MagicMock(), None, mock.MagicMock())
        self.assertFalse(cc_disk_setup.is_disk_used(mock.MagicMock()))


class TestGetMbrHddSize(TestCase):

    def setUp(self):
        super(TestGetMbrHddSize, self).setUp()
        self.patches = ExitStack()
        self.subp = self.patches.enter_context(
            mock.patch.object(cc_disk_setup.util, 'subp'))

    def tearDown(self):
        super(TestGetMbrHddSize, self).tearDown()
        self.patches.close()

    def _configure_subp_mock(self, hdd_size_in_bytes, sector_size_in_bytes):
        def _subp(cmd, *args, **kwargs):
            self.assertEqual(3, len(cmd))
            if '--getsize64' in cmd:
                return hdd_size_in_bytes, None
            elif '--getss' in cmd:
                return sector_size_in_bytes, None
            raise Exception('Unexpected blockdev command called')

        self.subp.side_effect = _subp

    def _test_for_sector_size(self, sector_size):
        size_in_bytes = random.randint(10000, 10000000) * 512
        size_in_sectors = size_in_bytes / sector_size
        self._configure_subp_mock(size_in_bytes, sector_size)
        self.assertEqual(size_in_sectors,
                         cc_disk_setup.get_mbr_hdd_size('/dev/sda1'))

    def test_size_for_512_byte_sectors(self):
        self._test_for_sector_size(512)

    def test_size_for_1024_byte_sectors(self):
        self._test_for_sector_size(1024)

    def test_size_for_2048_byte_sectors(self):
        self._test_for_sector_size(2048)

    def test_size_for_4096_byte_sectors(self):
        self._test_for_sector_size(4096)


class TestGetPartitionMbrLayout(TestCase):

    def test_single_partition_using_boolean(self):
        self.assertEqual('0,',
                         cc_disk_setup.get_partition_mbr_layout(1000, True))

    def test_single_partition_using_list(self):
        disk_size = random.randint(1000000, 1000000000000)
        self.assertEqual(
            ',,83',
            cc_disk_setup.get_partition_mbr_layout(disk_size, [100]))

    def test_half_and_half(self):
        disk_size = random.randint(1000000, 1000000000000)
        expected_partition_size = int(float(disk_size) / 2)
        self.assertEqual(
            ',{0},83\n,,83'.format(expected_partition_size),
            cc_disk_setup.get_partition_mbr_layout(disk_size, [50, 50]))

    def test_thirds_with_different_partition_type(self):
        disk_size = random.randint(1000000, 1000000000000)
        expected_partition_size = int(float(disk_size) * 0.33)
        self.assertEqual(
            ',{0},83\n,,82'.format(expected_partition_size),
            cc_disk_setup.get_partition_mbr_layout(disk_size, [33, [66, 82]]))

# vi: ts=4 expandtab
