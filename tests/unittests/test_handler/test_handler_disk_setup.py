# This file is part of cloud-init. See LICENSE file for license information.

import random

from cloudinit.config import cc_disk_setup
from cloudinit.tests.helpers import CiTestCase, ExitStack, mock, TestCase


class TestIsDiskUsed(TestCase):

    def setUp(self):
        super(TestIsDiskUsed, self).setUp()
        self.patches = ExitStack()
        mod_name = 'cloudinit.config.cc_disk_setup'
        self.enumerate_disk = self.patches.enter_context(
            mock.patch('{0}.enumerate_disk'.format(mod_name)))
        self.check_fs = self.patches.enter_context(
            mock.patch('{0}.check_fs'.format(mod_name)))

    def tearDown(self):
        super(TestIsDiskUsed, self).tearDown()
        self.patches.close()

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
                         cc_disk_setup.get_hdd_size('/dev/sda1'))

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


class TestUpdateFsSetupDevices(TestCase):
    def test_regression_1634678(self):
        # Cf. https://bugs.launchpad.net/cloud-init/+bug/1634678
        fs_setup = {
            'partition': 'auto',
            'device': '/dev/xvdb1',
            'overwrite': False,
            'label': 'test',
            'filesystem': 'ext4'
        }

        cc_disk_setup.update_fs_setup_devices([fs_setup],
                                              lambda device: device)

        self.assertEqual({
            '_origname': '/dev/xvdb1',
            'partition': 'auto',
            'device': '/dev/xvdb1',
            'overwrite': False,
            'label': 'test',
            'filesystem': 'ext4'
        }, fs_setup)

    def test_dotted_devname(self):
        fs_setup = {
            'partition': 'auto',
            'device': 'ephemeral0.0',
            'label': 'test2',
            'filesystem': 'xfs'
        }

        cc_disk_setup.update_fs_setup_devices([fs_setup],
                                              lambda device: device)

        self.assertEqual({
            '_origname': 'ephemeral0.0',
            '_partition': 'auto',
            'partition': '0',
            'device': 'ephemeral0',
            'label': 'test2',
            'filesystem': 'xfs'
        }, fs_setup)

    def test_dotted_devname_populates_partition(self):
        fs_setup = {
            'device': 'ephemeral0.1',
            'label': 'test2',
            'filesystem': 'xfs'
        }
        cc_disk_setup.update_fs_setup_devices([fs_setup],
                                              lambda device: device)
        self.assertEqual({
            '_origname': 'ephemeral0.1',
            'device': 'ephemeral0',
            'partition': '1',
            'label': 'test2',
            'filesystem': 'xfs'
        }, fs_setup)


@mock.patch('cloudinit.config.cc_disk_setup.assert_and_settle_device',
            return_value=None)
@mock.patch('cloudinit.config.cc_disk_setup.find_device_node',
            return_value=('/dev/xdb1', False))
@mock.patch('cloudinit.config.cc_disk_setup.device_type', return_value=None)
@mock.patch('cloudinit.config.cc_disk_setup.util.subp', return_value=('', ''))
class TestMkfsCommandHandling(CiTestCase):

    with_logs = True

    def test_with_cmd(self, subp, *args):
        """mkfs honors cmd and logs warnings when extra_opts or overwrite are
        provided."""
        cc_disk_setup.mkfs({
            'cmd': 'mkfs -t %(filesystem)s -L %(label)s %(device)s',
            'filesystem': 'ext4',
            'device': '/dev/xdb1',
            'label': 'with_cmd',
            'extra_opts': ['should', 'generate', 'warning'],
            'overwrite': 'should generate warning too'
        })

        self.assertIn(
            'extra_opts ' +
            'ignored because cmd was specified: mkfs -t ext4 -L with_cmd ' +
            '/dev/xdb1',
            self.logs.getvalue())
        self.assertIn(
            'overwrite ' +
            'ignored because cmd was specified: mkfs -t ext4 -L with_cmd ' +
            '/dev/xdb1',
            self.logs.getvalue())

        subp.assert_called_once_with(
            'mkfs -t ext4 -L with_cmd /dev/xdb1', shell=True)

    @mock.patch('cloudinit.config.cc_disk_setup.util.which')
    def test_overwrite_and_extra_opts_without_cmd(self, m_which, subp, *args):
        """mkfs observes extra_opts and overwrite settings when cmd is not
        present."""
        m_which.side_effect = lambda p: {'mkfs.ext4': '/sbin/mkfs.ext4'}[p]
        cc_disk_setup.mkfs({
            'filesystem': 'ext4',
            'device': '/dev/xdb1',
            'label': 'without_cmd',
            'extra_opts': ['are', 'added'],
            'overwrite': True
        })

        subp.assert_called_once_with(
            ['/sbin/mkfs.ext4', '/dev/xdb1',
             '-L', 'without_cmd', '-F', 'are', 'added'],
            shell=False)

# vi: ts=4 expandtab
