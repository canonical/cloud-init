# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import cloud
from cloudinit.config import cc_growpart
from cloudinit import util

from cloudinit.tests.helpers import CiTestCase, mock


import errno
import logging
import os
import re

try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

# growpart:
#   mode: auto  # off, on, auto, 'growpart'
#   devices: ['root']

HELP_GROWPART_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
    -u | --update  R  update the the kernel partition table info after growing
                      this requires kernel support and 'partx --update'
                      R is one of:
                       - 'auto'  : [default] update partition if possible
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

HELP_GROWPART_NO_RESIZE = """
growpart disk partition
   rewrite partition table so that partition takes up all the space it can
   options:
    -h | --help       print Usage and exit
<SNIP>
   Example:
    - growpart /dev/sda 1
      Resize partition 1 on /dev/sda
"""

HELP_GPART = """
usage: gpart add -t type [-a alignment] [-b start] <SNIP> geom
       gpart backup geom
       gpart bootcode [-b bootcode] [-p partcode -i index] [-f flags] geom
<SNIP>
       gpart resize -i index [-a alignment] [-s size] [-f flags] geom
       gpart restore [-lF] [-f flags] provider [...]
       gpart recover [-f flags] geom
       gpart help
<SNIP>
"""

GROWPART_CHANGED_1 = (
    "CHANGED: resizer=sfdisk partition=1 start=2048 old: size=1021952 "
    "end=1024000 new: size=2045919 end=2047967")
GROWPART_CHANGED_2 = (
    "CHANGED: partition=1 start=2048 old: size=1021952 end=1024000 new: "
    "size=2045919,end=2047967")
GROWPART_NOCHANGE_1 = (
    "NOCHANGE: partition 1 is size 83883999. it cannot be grown")


class TestDisabled(CiTestCase):
    def setUp(self):
        super(TestDisabled, self).setUp()
        self.name = "growpart"
        self.cloud_init = None
        self.log = logging.getLogger("TestDisabled")
        self.args = []

        self.handle = cc_growpart.handle

    def test_mode_off(self):
        # Test that nothing is done if mode is off.

        # this really only verifies that resizer_factory isn't called
        config = {'growpart': {'mode': 'off'}}

        with mock.patch.object(cc_growpart, 'resizer_factory') as mockobj:
            self.handle(self.name, config, self.cloud_init, self.log,
                        self.args)
            self.assertEqual(mockobj.call_count, 0)


class TestConfig(CiTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "growpart"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestConfig")
        self.args = []

        self.cloud_init = None
        self.handle = cc_growpart.handle

    @mock.patch.dict("os.environ", clear=True)
    def test_no_resizers_auto_is_fine(self):
        with mock.patch.object(
                util, 'subp',
                return_value=(HELP_GROWPART_NO_RESIZE, "")) as mockobj:

            config = {'growpart': {'mode': 'auto'}}
            self.handle(self.name, config, self.cloud_init, self.log,
                        self.args)

            mockobj.assert_has_calls([
                mock.call(['growpart', '--help'], env={'LANG': 'C'}),
                mock.call(['gpart', 'help'], env={'LANG': 'C'}, rcs=[0, 1])])

    @mock.patch.dict("os.environ", clear=True)
    def test_no_resizers_mode_growpart_is_exception(self):
        with mock.patch.object(
                util, 'subp',
                return_value=(HELP_GROWPART_NO_RESIZE, "")) as mockobj:
            config = {'growpart': {'mode': "growpart"}}
            self.assertRaises(
                ValueError, self.handle, self.name, config,
                self.cloud_init, self.log, self.args)

            mockobj.assert_called_once_with(
                ['growpart', '--help'], env={'LANG': 'C'})

    @mock.patch.dict("os.environ", clear=True)
    def test_mode_auto_prefers_growpart(self):
        with mock.patch.object(
                util, 'subp',
                return_value=(HELP_GROWPART_RESIZE, "")) as mockobj:
            ret = cc_growpart.resizer_factory(mode="auto")
            self.assertIsInstance(ret, cc_growpart.ResizeGrowPart)

            mockobj.assert_called_once_with(
                ['growpart', '--help'], env={'LANG': 'C'})

    @mock.patch.dict("os.environ", clear=True)
    def test_mode_auto_falls_back_to_gpart(self):
        with mock.patch.object(
                util, 'subp',
                return_value=("", HELP_GPART)) as mockobj:
            ret = cc_growpart.resizer_factory(mode="auto")
            self.assertIsInstance(ret, cc_growpart.ResizeGpart)

            mockobj.assert_has_calls([
                mock.call(['growpart', '--help'], env={'LANG': 'C'}),
                mock.call(['gpart', 'help'], env={'LANG': 'C'}, rcs=[0, 1])])

    def test_handle_with_no_growpart_entry(self):
        # if no 'growpart' entry in config, then mode=auto should be used

        myresizer = object()
        retval = (("/", cc_growpart.RESIZE.CHANGED, "my-message",),)

        with ExitStack() as mocks:
            factory = mocks.enter_context(
                mock.patch.object(cc_growpart, 'resizer_factory',
                                  return_value=myresizer))
            rsdevs = mocks.enter_context(
                mock.patch.object(cc_growpart, 'resize_devices',
                                  return_value=retval))
            mocks.enter_context(
                mock.patch.object(cc_growpart, 'RESIZERS',
                                  (('mysizer', object),)
                                  ))

            self.handle(self.name, {}, self.cloud_init, self.log, self.args)

            factory.assert_called_once_with('auto')
            rsdevs.assert_called_once_with(myresizer, ['/'])


class TestResize(CiTestCase):
    def setUp(self):
        super(TestResize, self).setUp()
        self.name = "growpart"
        self.log = logging.getLogger("TestResize")

    def test_simple_devices(self):
        # test simple device list
        # this patches out devent2dev, os.stat, and device_part_info
        # so in the end, doesn't test a lot
        devs = ["/dev/XXda1", "/dev/disk/by-partuuid/123-111"]
        # test the os.path.realpath code
        devsym = {"/dev/disk/by-partuuid/123-111": "/dev/YYda2"}
        devstat_ret = Bunch(st_mode=25008, st_ino=6078, st_dev=5,
                            st_nlink=1, st_uid=0, st_gid=6, st_size=0,
                            st_atime=0, st_mtime=0, st_ctime=0)
        enoent = ["/dev/NOENT"]
        real_stat = os.stat
        real_realpath = os.path.realpath
        resize_calls = []

        class myresizer(object):
            def resize(self, diskdev, partnum, partdev):
                resize_calls.append((diskdev, partnum, partdev))
                if partdev == "/dev/YYda2":
                    return (1024, 2048)
                return (1024, 1024)  # old size, new size

        def mystat(path):
            if path in devs or path in devsym.values():
                return devstat_ret
            if path in enoent:
                e = OSError("%s: does not exist" % path)
                e.errno = errno.ENOENT
                raise e
            return real_stat(path)

        def myrealpath(path):
            if path in devsym:
                r = devsym[path]
            else:
                r = real_realpath(path)
            return r

        try:
            opinfo = cc_growpart.device_part_info
            cc_growpart.device_part_info = simple_device_part_info
            os.stat = mystat
            os.path.realpath = myrealpath

            resized = cc_growpart.resize_devices(myresizer(), devs + enoent)

            def find(name, res):
                for f in res:
                    if f[0] == name:
                        return f
                return None

            self.assertEqual(cc_growpart.RESIZE.NOCHANGE,
                             find("/dev/XXda1", resized)[1])
            self.assertEqual(cc_growpart.RESIZE.CHANGED,
                             find("/dev/disk/by-partuuid/123-111", resized)[1])
            self.assertEqual(cc_growpart.RESIZE.SKIPPED,
                             find(enoent[0], resized)[1])
            self.assertEqual(resize_calls,
                             [("/dev/XXda", "1", "/dev/XXda1"),
                              ("/dev/YYda", "2", "/dev/YYda2")])
        finally:
            cc_growpart.device_part_info = opinfo
            os.stat = real_stat
            os.path.realpath = real_realpath


class TestGetSize(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestGetSize, self).setUp()
        self.root = self.tmp_dir()
        self.mypart = self.root + "/mydiskp1"
        util.write_file(self.mypart, "Dang JJ!")

    def test_get_size(self):
        self.assertEqual(8, cc_growpart.get_size(self.mypart))

    def test_get_size_errors(self):
        with self.assertRaises(OSError):
            cc_growpart.get_size(self.random_string())


class TestResizeGrowPart(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestResizeGrowPart, self).setUp()
        self.resizer = cc_growpart.ResizeGrowPart()
        self.add_patch('cloudinit.config.cc_growpart.util.subp', 'm_subp')
        self.add_patch('cloudinit.config.cc_growpart.util.multi_log', 'm_mlog')

    def test_get_size(self):
        self.assertEqual(('523239424', '1047510528'),
                         self.resizer.get_size(GROWPART_CHANGED_1))

    def test_get_size_older_release(self):
        self.assertEqual(('523239424', '1047510528'),
                         self.resizer.get_size(GROWPART_CHANGED_2))

    def test_get_size_no_change(self):
        self.assertEqual(('42948607488', '42948607488'),
                         self.resizer.get_size(GROWPART_NOCHANGE_1))

    def test_get_size_error_raises_valueerror_exception(self):
        with self.assertRaises(ValueError):
            self.resizer.get_size(self.random_string())

    def test_get_size_raises_valuerror_bad_change_nochange_output(self):
        with self.assertRaises(ValueError):
            self.resizer.get_size("CHANGED:" + self.random_string())
        with self.assertRaises(ValueError):
            self.resizer.get_size("NOCHANGE:" + self.random_string())

    def test_resize_changed(self):
        diskdev = self.random_string()
        partnum = "1"
        partdev = "%sp%s" % (diskdev, partnum)
        self.m_subp.return_value = (GROWPART_CHANGED_1, "")
        self.assertEqual(('523239424', '1047510528'),
                         self.resizer.resize(diskdev, partnum, partdev))
        self.assertEqual(1, len(self.m_subp.call_args_list))
        self.assertEqual(
            mock.call(['growpart', '-v', diskdev, partnum], rcs=[0, 1]),
            self.m_subp.call_args_list[0])

    def test_resize_nochange(self):
        diskdev = self.random_string()
        partnum = "1"
        partdev = "%sp%s" % (diskdev, partnum)
        self.m_subp.return_value = (GROWPART_NOCHANGE_1, "")
        self.assertEqual(('42948607488', '42948607488'),
                         self.resizer.resize(diskdev, partnum, partdev))
        self.assertEqual(1, len(self.m_subp.call_args_list))
        self.assertEqual(
            mock.call(['growpart', '-v', diskdev, partnum], rcs=[0, 1]),
            self.m_subp.call_args_list[0])

    def test_resize_raise_on_other_exit_code_errors(self):
        diskdev = self.random_string()
        partnum = "1"
        partdev = "%sp%s" % (diskdev, partnum)
        self.m_subp.side_effect = util.ProcessExecutionError(stdout="",
                                                             stderr="Error",
                                                             exit_code=2)
        with self.assertRaises(cc_growpart.ResizeFailedException):
            self.resizer.resize(diskdev, partnum, partdev)
        self.assertEqual(1, len(self.m_subp.call_args_list))
        self.assertEqual(
            mock.call(['growpart', '-v', diskdev, partnum], rcs=[0, 1]),
            self.m_subp.call_args_list[0])


def simple_device_part_info(devpath):
    # simple stupid return (/dev/vda, 1) for /dev/vda
    ret = re.search("([^0-9]*)([0-9]*)$", devpath)
    x = (ret.group(1), ret.group(2))
    return x


class Bunch(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


# vi: ts=4 expandtab
