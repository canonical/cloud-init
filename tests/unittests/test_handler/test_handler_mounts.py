# This file is part of cloud-init. See LICENSE file for license information.

import os.path
from unittest import mock

from cloudinit.config import cc_mounts

from cloudinit.tests import helpers as test_helpers


class TestSanitizeDevname(test_helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestSanitizeDevname, self).setUp()
        self.new_root = self.tmp_dir()
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

    def test_network_device_returns_network_device(self):
        disk_path = 'netdevice:/path'
        self.assertEqual(
            disk_path,
            cc_mounts.sanitize_devname(disk_path, None, mock.Mock()))


class TestSwapFileCreation(test_helpers.FilesystemMockingTestCase):

    def setUp(self):
        super(TestSwapFileCreation, self).setUp()
        self.new_root = self.tmp_dir()
        self.patchOS(self.new_root)

        self.fstab_path = os.path.join(self.new_root, 'etc/fstab')
        self.swap_path = os.path.join(self.new_root, 'swap.img')
        self._makedirs('/etc')

        self.add_patch('cloudinit.config.cc_mounts.FSTAB_PATH',
                       'mock_fstab_path',
                       self.fstab_path,
                       autospec=False)

        self.add_patch('cloudinit.config.cc_mounts.subp.subp',
                       'm_subp_subp')

        self.add_patch('cloudinit.config.cc_mounts.util.mounts',
                       'mock_util_mounts',
                       return_value={
                           '/dev/sda1': {'fstype': 'ext4',
                                         'mountpoint': '/',
                                         'opts': 'rw,relatime,discard'
                                         }})

        self.mock_cloud = mock.Mock()
        self.mock_log = mock.Mock()
        self.mock_cloud.device_name_to_device = self.device_name_to_device

        self.cc = {
            'swap': {
                'filename': self.swap_path,
                'size': '512',
                'maxsize': '512'}}

    def _makedirs(self, directory):
        directory = os.path.join(self.new_root, directory.lstrip('/'))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def device_name_to_device(self, path):
        if path == 'swap':
            return self.swap_path
        else:
            dev = None

        return dev

    @mock.patch('cloudinit.util.get_mount_info')
    @mock.patch('cloudinit.util.kernel_version')
    def test_swap_creation_method_fallocate_on_xfs(self, m_kernel_version,
                                                   m_get_mount_info):
        m_kernel_version.return_value = (4, 20)
        m_get_mount_info.return_value = ["", "xfs"]

        cc_mounts.handle(None, self.cc, self.mock_cloud, self.mock_log, [])
        self.m_subp_subp.assert_has_calls([
            mock.call(['fallocate', '-l', '0M', self.swap_path], capture=True),
            mock.call(['mkswap', self.swap_path]),
            mock.call(['swapon', '-a'])])

    @mock.patch('cloudinit.util.get_mount_info')
    @mock.patch('cloudinit.util.kernel_version')
    def test_swap_creation_method_xfs(self, m_kernel_version,
                                      m_get_mount_info):
        m_kernel_version.return_value = (3, 18)
        m_get_mount_info.return_value = ["", "xfs"]

        cc_mounts.handle(None, self.cc, self.mock_cloud, self.mock_log, [])
        self.m_subp_subp.assert_has_calls([
            mock.call(['dd', 'if=/dev/zero',
                       'of=' + self.swap_path,
                       'bs=1M', 'count=0'], capture=True),
            mock.call(['mkswap', self.swap_path]),
            mock.call(['swapon', '-a'])])

    @mock.patch('cloudinit.util.get_mount_info')
    @mock.patch('cloudinit.util.kernel_version')
    def test_swap_creation_method_btrfs(self, m_kernel_version,
                                        m_get_mount_info):
        m_kernel_version.return_value = (4, 20)
        m_get_mount_info.return_value = ["", "btrfs"]

        cc_mounts.handle(None, self.cc, self.mock_cloud, self.mock_log, [])
        self.m_subp_subp.assert_has_calls([
            mock.call(['dd', 'if=/dev/zero',
                       'of=' + self.swap_path,
                       'bs=1M', 'count=0'], capture=True),
            mock.call(['mkswap', self.swap_path]),
            mock.call(['swapon', '-a'])])

    @mock.patch('cloudinit.util.get_mount_info')
    @mock.patch('cloudinit.util.kernel_version')
    def test_swap_creation_method_ext4(self, m_kernel_version,
                                       m_get_mount_info):
        m_kernel_version.return_value = (5, 14)
        m_get_mount_info.return_value = ["", "ext4"]

        cc_mounts.handle(None, self.cc, self.mock_cloud, self.mock_log, [])
        self.m_subp_subp.assert_has_calls([
            mock.call(['fallocate', '-l', '0M', self.swap_path], capture=True),
            mock.call(['mkswap', self.swap_path]),
            mock.call(['swapon', '-a'])])


class TestFstabHandling(test_helpers.FilesystemMockingTestCase):

    swap_path = '/dev/sdb1'

    def setUp(self):
        super(TestFstabHandling, self).setUp()
        self.new_root = self.tmp_dir()
        self.patchOS(self.new_root)

        self.fstab_path = os.path.join(self.new_root, 'etc/fstab')
        self._makedirs('/etc')

        self.add_patch('cloudinit.config.cc_mounts.FSTAB_PATH',
                       'mock_fstab_path',
                       self.fstab_path,
                       autospec=False)

        self.add_patch('cloudinit.config.cc_mounts._is_block_device',
                       'mock_is_block_device',
                       return_value=True)

        self.add_patch('cloudinit.config.cc_mounts.subp.subp',
                       'm_subp_subp')

        self.add_patch('cloudinit.config.cc_mounts.util.mounts',
                       'mock_util_mounts',
                       return_value={
                           '/dev/sda1': {'fstype': 'ext4',
                                         'mountpoint': '/',
                                         'opts': 'rw,relatime,discard'
                                         }})

        self.mock_cloud = mock.Mock()
        self.mock_log = mock.Mock()
        self.mock_cloud.device_name_to_device = self.device_name_to_device

    def _makedirs(self, directory):
        directory = os.path.join(self.new_root, directory.lstrip('/'))
        if not os.path.exists(directory):
            os.makedirs(directory)

    def device_name_to_device(self, path):
        if path == 'swap':
            return self.swap_path
        else:
            dev = None

        return dev

    def test_no_fstab(self):
        """ Handle images which do not include an fstab. """
        self.assertFalse(os.path.exists(cc_mounts.FSTAB_PATH))
        fstab_expected_content = (
            '%s\tnone\tswap\tsw,comment=cloudconfig\t'
            '0\t0\n' % (self.swap_path,)
        )
        cc_mounts.handle(None, {}, self.mock_cloud, self.mock_log, [])
        with open(cc_mounts.FSTAB_PATH, 'r') as fd:
            fstab_new_content = fd.read()
            self.assertEqual(fstab_expected_content, fstab_new_content)

    def test_swap_integrity(self):
        '''Ensure that the swap file is correctly created and can
        swapon successfully. Fixing the corner case of:
        kernel: swapon: swapfile has holes'''

        fstab = '/swap.img swap swap defaults 0 0\n'

        with open(cc_mounts.FSTAB_PATH, 'w') as fd:
            fd.write(fstab)
        cc = {'swap': ['filename: /swap.img', 'size: 512', 'maxsize: 512']}
        cc_mounts.handle(None, cc, self.mock_cloud, self.mock_log, [])

    def test_fstab_no_swap_device(self):
        '''Ensure that cloud-init adds a discovered swap partition
        to /etc/fstab.'''

        fstab_original_content = ''
        fstab_expected_content = (
            '%s\tnone\tswap\tsw,comment=cloudconfig\t'
            '0\t0\n' % (self.swap_path,)
        )

        with open(cc_mounts.FSTAB_PATH, 'w') as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle(None, {}, self.mock_cloud, self.mock_log, [])

        with open(cc_mounts.FSTAB_PATH, 'r') as fd:
            fstab_new_content = fd.read()
            self.assertEqual(fstab_expected_content, fstab_new_content)

    def test_fstab_same_swap_device_already_configured(self):
        '''Ensure that cloud-init will not add a swap device if the same
        device already exists in /etc/fstab.'''

        fstab_original_content = '%s swap swap defaults 0 0\n' % (
            self.swap_path,)
        fstab_expected_content = fstab_original_content

        with open(cc_mounts.FSTAB_PATH, 'w') as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle(None, {}, self.mock_cloud, self.mock_log, [])

        with open(cc_mounts.FSTAB_PATH, 'r') as fd:
            fstab_new_content = fd.read()
            self.assertEqual(fstab_expected_content, fstab_new_content)

    def test_fstab_alternate_swap_device_already_configured(self):
        '''Ensure that cloud-init will add a discovered swap device to
        /etc/fstab even when there exists a swap definition on another
        device.'''

        fstab_original_content = '/dev/sdc1 swap swap defaults 0 0\n'
        fstab_expected_content = (
            fstab_original_content +
            '%s\tnone\tswap\tsw,comment=cloudconfig\t'
            '0\t0\n' % (self.swap_path,)
        )

        with open(cc_mounts.FSTAB_PATH, 'w') as fd:
            fd.write(fstab_original_content)

        cc_mounts.handle(None, {}, self.mock_cloud, self.mock_log, [])

        with open(cc_mounts.FSTAB_PATH, 'r') as fd:
            fstab_new_content = fd.read()
            self.assertEqual(fstab_expected_content, fstab_new_content)

    def test_no_change_fstab_sets_needs_mount_all(self):
        '''verify unchanged fstab entries are mounted if not call mount -a'''
        fstab_original_content = (
            'LABEL=cloudimg-rootfs / ext4 defaults 0 0\n'
            'LABEL=UEFI /boot/efi vfat defaults 0 0\n'
            '/dev/vdb /mnt auto defaults,noexec,comment=cloudconfig 0 2\n'
        )
        fstab_expected_content = fstab_original_content
        cc = {
            'mounts': [
                ['/dev/vdb', '/mnt', 'auto', 'defaults,noexec']
            ]
        }
        with open(cc_mounts.FSTAB_PATH, 'w') as fd:
            fd.write(fstab_original_content)
        with open(cc_mounts.FSTAB_PATH, 'r') as fd:
            fstab_new_content = fd.read()
            self.assertEqual(fstab_expected_content, fstab_new_content)
        cc_mounts.handle(None, cc, self.mock_cloud, self.mock_log, [])
        self.m_subp_subp.assert_has_calls([
            mock.call(['mount', '-a']),
            mock.call(['systemctl', 'daemon-reload'])])

# vi: ts=4 expandtab
