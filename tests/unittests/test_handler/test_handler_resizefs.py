# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config.cc_resizefs import (
    can_skip_resize, handle, maybe_get_writable_device_path, _resize_btrfs,
    _resize_zfs, _resize_xfs, _resize_ext, _resize_ufs)

from collections import namedtuple
import logging
import textwrap

from cloudinit.tests.helpers import (
    CiTestCase, mock, skipUnlessJsonSchema, util, wrap_and_call)


LOG = logging.getLogger(__name__)


class TestResizefs(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestResizefs, self).setUp()
        self.name = "resizefs"

    @mock.patch('cloudinit.config.cc_resizefs._get_dumpfs_output')
    @mock.patch('cloudinit.config.cc_resizefs._get_gpart_output')
    def test_skip_ufs_resize(self, gpart_out, dumpfs_out):
        fs_type = "ufs"
        resize_what = "/"
        devpth = "/dev/da0p2"
        dumpfs_out.return_value = (
            "# newfs command for / (/dev/label/rootfs)\n"
            "newfs -O 2 -U -a 4 -b 32768 -d 32768 -e 4096 "
            "-f 4096 -g 16384 -h 64 -i 8192 -j -k 6408 -m 8 "
            "-o time -s 58719232 /dev/label/rootfs\n")
        gpart_out.return_value = textwrap.dedent("""\
            =>      40  62914480  da0  GPT  (30G)
                    40      1024    1  freebsd-boot  (512K)
                  1064  58719232    2  freebsd-ufs  (28G)
              58720296   3145728    3  freebsd-swap  (1.5G)
              61866024   1048496       - free -  (512M)
            """)
        res = can_skip_resize(fs_type, resize_what, devpth)
        self.assertTrue(res)

    @mock.patch('cloudinit.config.cc_resizefs._get_dumpfs_output')
    @mock.patch('cloudinit.config.cc_resizefs._get_gpart_output')
    def test_skip_ufs_resize_roundup(self, gpart_out, dumpfs_out):
        fs_type = "ufs"
        resize_what = "/"
        devpth = "/dev/da0p2"
        dumpfs_out.return_value = (
            "# newfs command for / (/dev/label/rootfs)\n"
            "newfs -O 2 -U -a 4 -b 32768 -d 32768 -e 4096 "
            "-f 4096 -g 16384 -h 64 -i 8192 -j -k 368 -m 8 "
            "-o time -s 297080 /dev/label/rootfs\n")
        gpart_out.return_value = textwrap.dedent("""\
            =>      34  297086  da0  GPT  (145M)
                    34  297086    1  freebsd-ufs  (145M)
            """)
        res = can_skip_resize(fs_type, resize_what, devpth)
        self.assertTrue(res)

    def test_can_skip_resize_ext(self):
        self.assertFalse(can_skip_resize('ext', '/', '/dev/sda1'))

    def test_handle_noops_on_disabled(self):
        """The handle function logs when the configuration disables resize."""
        cfg = {'resize_rootfs': False}
        handle('cc_resizefs', cfg, _cloud=None, log=LOG, args=[])
        self.assertIn(
            'DEBUG: Skipping module named cc_resizefs, resizing disabled\n',
            self.logs.getvalue())

    @skipUnlessJsonSchema()
    def test_handle_schema_validation_logs_invalid_resize_rootfs_value(self):
        """The handle reports json schema violations as a warning.

        Invalid values for resize_rootfs result in disabling the module.
        """
        cfg = {'resize_rootfs': 'junk'}
        handle('cc_resizefs', cfg, _cloud=None, log=LOG, args=[])
        logs = self.logs.getvalue()
        self.assertIn(
            "WARNING: Invalid config:\nresize_rootfs: 'junk' is not one of"
            " [True, False, 'noblock']",
            logs)
        self.assertIn(
            'DEBUG: Skipping module named cc_resizefs, resizing disabled\n',
            logs)

    @mock.patch('cloudinit.config.cc_resizefs.util.get_mount_info')
    def test_handle_warns_on_unknown_mount_info(self, m_get_mount_info):
        """handle warns when get_mount_info sees unknown filesystem for /."""
        m_get_mount_info.return_value = None
        cfg = {'resize_rootfs': True}
        handle('cc_resizefs', cfg, _cloud=None, log=LOG, args=[])
        logs = self.logs.getvalue()
        self.assertNotIn("WARNING: Invalid config:\nresize_rootfs:", logs)
        self.assertIn(
            'WARNING: Could not determine filesystem type of /\n',
            logs)
        self.assertEqual(
            [mock.call('/', LOG)],
            m_get_mount_info.call_args_list)

    def test_handle_warns_on_undiscoverable_root_path_in_commandline(self):
        """handle noops when the root path is not found on the commandline."""
        cfg = {'resize_rootfs': True}
        exists_mock_path = 'cloudinit.config.cc_resizefs.os.path.exists'

        def fake_mount_info(path, log):
            self.assertEqual('/', path)
            self.assertEqual(LOG, log)
            return ('/dev/root', 'ext4', '/')

        with mock.patch(exists_mock_path) as m_exists:
            m_exists.return_value = False
            wrap_and_call(
                'cloudinit.config.cc_resizefs.util',
                {'is_container': {'return_value': False},
                 'get_mount_info': {'side_effect': fake_mount_info},
                 'get_cmdline': {'return_value': 'BOOT_IMAGE=/vmlinuz.efi'}},
                handle, 'cc_resizefs', cfg, _cloud=None, log=LOG,
                args=[])
        logs = self.logs.getvalue()
        self.assertIn("WARNING: Unable to find device '/dev/root'", logs)

    def test_resize_zfs_cmd_return(self):
        zpool = 'zroot'
        devpth = 'gpt/system'
        self.assertEqual(('zpool', 'online', '-e', zpool, devpth),
                         _resize_zfs(zpool, devpth))

    def test_resize_xfs_cmd_return(self):
        mount_point = '/mnt/test'
        devpth = '/dev/sda1'
        self.assertEqual(('xfs_growfs', mount_point),
                         _resize_xfs(mount_point, devpth))

    def test_resize_ext_cmd_return(self):
        mount_point = '/'
        devpth = '/dev/sdb1'
        self.assertEqual(('resize2fs', devpth),
                         _resize_ext(mount_point, devpth))

    def test_resize_ufs_cmd_return(self):
        mount_point = '/'
        devpth = '/dev/sda2'
        self.assertEqual(('growfs', '-y', devpth),
                         _resize_ufs(mount_point, devpth))

    @mock.patch('cloudinit.util.is_container', return_value=False)
    @mock.patch('cloudinit.util.parse_mount')
    @mock.patch('cloudinit.util.get_device_info_from_zpool')
    @mock.patch('cloudinit.util.get_mount_info')
    def test_handle_zfs_root(self, mount_info, zpool_info, parse_mount,
                             is_container):
        devpth = 'vmzroot/ROOT/freebsd'
        disk = 'gpt/system'
        fs_type = 'zfs'
        mount_point = '/'

        mount_info.return_value = (devpth, fs_type, mount_point)
        zpool_info.return_value = disk
        parse_mount.return_value = (devpth, fs_type, mount_point)

        cfg = {'resize_rootfs': True}

        with mock.patch('cloudinit.config.cc_resizefs.do_resize') as dresize:
            handle('cc_resizefs', cfg, _cloud=None, log=LOG, args=[])
            ret = dresize.call_args[0][0]

        self.assertEqual(('zpool', 'online', '-e', 'vmzroot', disk), ret)

    @mock.patch('cloudinit.util.is_container', return_value=False)
    @mock.patch('cloudinit.util.get_mount_info')
    @mock.patch('cloudinit.util.get_device_info_from_zpool')
    @mock.patch('cloudinit.util.parse_mount')
    def test_handle_modern_zfsroot(self, mount_info, zpool_info, parse_mount,
                                   is_container):
        devpth = 'zroot/ROOT/default'
        disk = 'da0p3'
        fs_type = 'zfs'
        mount_point = '/'

        mount_info.return_value = (devpth, fs_type, mount_point)
        zpool_info.return_value = disk
        parse_mount.return_value = (devpth, fs_type, mount_point)

        cfg = {'resize_rootfs': True}

        def fake_stat(devpath):
            if devpath == disk:
                raise OSError("not here")
            FakeStat = namedtuple(
                'FakeStat', ['st_mode', 'st_size', 'st_mtime'])  # minimal stat
            return FakeStat(25008, 0, 1)  # fake char block device

        with mock.patch('cloudinit.config.cc_resizefs.do_resize') as dresize:
            with mock.patch('cloudinit.config.cc_resizefs.os.stat') as m_stat:
                m_stat.side_effect = fake_stat
                handle('cc_resizefs', cfg, _cloud=None, log=LOG, args=[])

        self.assertEqual(('zpool', 'online', '-e', 'zroot', '/dev/' + disk),
                         dresize.call_args[0][0])


class TestRootDevFromCmdline(CiTestCase):

    def test_rootdev_from_cmdline_with_no_root(self):
        """Return None from rootdev_from_cmdline when root is not present."""
        invalid_cases = [
            'BOOT_IMAGE=/adsf asdfa werasef  root adf', 'BOOT_IMAGE=/adsf', '']
        for case in invalid_cases:
            self.assertIsNone(util.rootdev_from_cmdline(case))

    def test_rootdev_from_cmdline_with_root_startswith_dev(self):
        """Return the cmdline root when the path starts with /dev."""
        self.assertEqual(
            '/dev/this', util.rootdev_from_cmdline('asdf root=/dev/this'))

    def test_rootdev_from_cmdline_with_root_without_dev_prefix(self):
        """Add /dev prefix to cmdline root when the path lacks the prefix."""
        self.assertEqual(
            '/dev/this', util.rootdev_from_cmdline('asdf root=this'))

    def test_rootdev_from_cmdline_with_root_with_label(self):
        """When cmdline root contains a LABEL, our root is disk/by-label."""
        self.assertEqual(
            '/dev/disk/by-label/unique',
            util.rootdev_from_cmdline('asdf root=LABEL=unique'))

    def test_rootdev_from_cmdline_with_root_with_uuid(self):
        """When cmdline root contains a UUID, our root is disk/by-uuid."""
        self.assertEqual(
            '/dev/disk/by-uuid/adsfdsaf-adsf',
            util.rootdev_from_cmdline('asdf root=UUID=adsfdsaf-adsf'))


class TestMaybeGetDevicePathAsWritableBlock(CiTestCase):

    with_logs = True

    def test_maybe_get_writable_device_path_none_on_overlayroot(self):
        """When devpath is overlayroot (on MAAS), is_dev_writable is False."""
        info = 'does not matter'
        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs.util',
            {'is_container': {'return_value': False}},
            maybe_get_writable_device_path, 'overlayroot', info, LOG)
        self.assertIsNone(devpath)
        self.assertIn(
            "Not attempting to resize devpath 'overlayroot'",
            self.logs.getvalue())

    def test_maybe_get_writable_device_path_warns_missing_cmdline_root(self):
        """When root does not exist isn't in the cmdline, log warning."""
        info = 'does not matter'

        def fake_mount_info(path, log):
            self.assertEqual('/', path)
            self.assertEqual(LOG, log)
            return ('/dev/root', 'ext4', '/')

        exists_mock_path = 'cloudinit.config.cc_resizefs.os.path.exists'
        with mock.patch(exists_mock_path) as m_exists:
            m_exists.return_value = False
            devpath = wrap_and_call(
                'cloudinit.config.cc_resizefs.util',
                {'is_container': {'return_value': False},
                 'get_mount_info': {'side_effect': fake_mount_info},
                 'get_cmdline': {'return_value': 'BOOT_IMAGE=/vmlinuz.efi'}},
                maybe_get_writable_device_path, '/dev/root', info, LOG)
        self.assertIsNone(devpath)
        logs = self.logs.getvalue()
        self.assertIn("WARNING: Unable to find device '/dev/root'", logs)

    def test_maybe_get_writable_device_path_does_not_exist(self):
        """When devpath does not exist, a warning is logged."""
        info = 'dev=/dev/I/dont/exist mnt_point=/ path=/dev/none'
        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs.util',
            {'is_container': {'return_value': False}},
            maybe_get_writable_device_path, '/dev/I/dont/exist', info, LOG)
        self.assertIsNone(devpath)
        self.assertIn(
            "WARNING: Device '/dev/I/dont/exist' did not exist."
            ' cannot resize: %s' % info,
            self.logs.getvalue())

    def test_maybe_get_writable_device_path_does_not_exist_in_container(self):
        """When devpath does not exist in a container, log a debug message."""
        info = 'dev=/dev/I/dont/exist mnt_point=/ path=/dev/none'
        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs.util',
            {'is_container': {'return_value': True}},
            maybe_get_writable_device_path, '/dev/I/dont/exist', info, LOG)
        self.assertIsNone(devpath)
        self.assertIn(
            "DEBUG: Device '/dev/I/dont/exist' did not exist in container."
            ' cannot resize: %s' % info,
            self.logs.getvalue())

    def test_maybe_get_writable_device_path_raises_oserror(self):
        """When unexpected OSError is raises by os.stat it is reraised."""
        info = 'dev=/dev/I/dont/exist mnt_point=/ path=/dev/none'
        with self.assertRaises(OSError) as context_manager:
            wrap_and_call(
                'cloudinit.config.cc_resizefs',
                {'util.is_container': {'return_value': True},
                 'os.stat': {'side_effect': OSError('Something unexpected')}},
                maybe_get_writable_device_path, '/dev/I/dont/exist', info, LOG)
        self.assertEqual(
            'Something unexpected', str(context_manager.exception))

    def test_maybe_get_writable_device_path_non_block(self):
        """When device is not a block device, emit warning return False."""
        fake_devpath = self.tmp_path('dev/readwrite')
        util.write_file(fake_devpath, '', mode=0o600)  # read-write
        info = 'dev=/dev/root mnt_point=/ path={0}'.format(fake_devpath)

        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs.util',
            {'is_container': {'return_value': False}},
            maybe_get_writable_device_path, fake_devpath, info, LOG)
        self.assertIsNone(devpath)
        self.assertIn(
            "WARNING: device '{0}' not a block device. cannot resize".format(
                fake_devpath),
            self.logs.getvalue())

    def test_maybe_get_writable_device_path_non_block_on_container(self):
        """When device is non-block device in container, emit debug log."""
        fake_devpath = self.tmp_path('dev/readwrite')
        util.write_file(fake_devpath, '', mode=0o600)  # read-write
        info = 'dev=/dev/root mnt_point=/ path={0}'.format(fake_devpath)

        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs.util',
            {'is_container': {'return_value': True}},
            maybe_get_writable_device_path, fake_devpath, info, LOG)
        self.assertIsNone(devpath)
        self.assertIn(
            "DEBUG: device '{0}' not a block device in container."
            ' cannot resize'.format(fake_devpath),
            self.logs.getvalue())

    def test_maybe_get_writable_device_path_returns_cmdline_root(self):
        """When root device is UUID in kernel commandline, update devpath."""
        # XXX Long-term we want to use FilesystemMocking test to avoid
        # touching os.stat.
        FakeStat = namedtuple(
            'FakeStat', ['st_mode', 'st_size', 'st_mtime'])  # minimal def.
        info = 'dev=/dev/root mnt_point=/ path=/does/not/matter'
        devpath = wrap_and_call(
            'cloudinit.config.cc_resizefs',
            {'util.get_cmdline': {'return_value': 'asdf root=UUID=my-uuid'},
             'util.is_container': False,
             'os.path.exists': False,  # /dev/root doesn't exist
             'os.stat': {
                 'return_value': FakeStat(25008, 0, 1)}  # char block device
             },
            maybe_get_writable_device_path, '/dev/root', info, LOG)
        self.assertEqual('/dev/disk/by-uuid/my-uuid', devpath)
        self.assertIn(
            "DEBUG: Converted /dev/root to '/dev/disk/by-uuid/my-uuid'"
            " per kernel cmdline",
            self.logs.getvalue())

    @mock.patch('cloudinit.util.mount_is_read_write')
    @mock.patch('cloudinit.config.cc_resizefs.os.path.isdir')
    def test_resize_btrfs_mount_is_ro(self, m_is_dir, m_is_rw):
        """Do not resize / directly if it is read-only. (LP: #1734787)."""
        m_is_rw.return_value = False
        m_is_dir.return_value = True
        self.assertEqual(
            ('btrfs', 'filesystem', 'resize', 'max', '//.snapshots'),
            _resize_btrfs("/", "/dev/sda1"))

    @mock.patch('cloudinit.util.mount_is_read_write')
    @mock.patch('cloudinit.config.cc_resizefs.os.path.isdir')
    def test_resize_btrfs_mount_is_rw(self, m_is_dir, m_is_rw):
        """Do not resize / directly if it is read-only. (LP: #1734787)."""
        m_is_rw.return_value = True
        m_is_dir.return_value = True
        self.assertEqual(
            ('btrfs', 'filesystem', 'resize', 'max', '/'),
            _resize_btrfs("/", "/dev/sda1"))

    @mock.patch('cloudinit.util.is_container', return_value=True)
    @mock.patch('cloudinit.util.is_FreeBSD')
    def test_maybe_get_writable_device_path_zfs_freebsd(self, freebsd,
                                                        m_is_container):
        freebsd.return_value = True
        info = 'dev=gpt/system mnt_point=/ path=/'
        devpth = maybe_get_writable_device_path('gpt/system', info, LOG)
        self.assertEqual('gpt/system', devpth)


# vi: ts=4 expandtab
