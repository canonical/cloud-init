# This file is part of cloud-init. See LICENSE file for license information.

import errno
import logging
import os
import re
import shutil
import stat
import unittest
from contextlib import ExitStack
from unittest import mock

from cloudinit import cloud, subp, temp_utils
from cloudinit.config import cc_growpart
from tests.unittests.helpers import TestCase

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


class Dir:
    """Stub object"""

    def __init__(self, name):
        self.name = name
        self.st_mode = name

    def is_dir(self, *args, **kwargs):
        return True

    def stat(self, *args, **kwargs):
        return self


class Scanner:
    """Stub object"""

    def __enter__(self):
        return (
            Dir(""),
            Dir(""),
        )

    def __exit__(self, *args):
        pass


class TestDisabled(unittest.TestCase):
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
        config = {"growpart": {"mode": "off"}}

        with mock.patch.object(cc_growpart, "resizer_factory") as mockobj:
            self.handle(
                self.name, config, self.cloud_init, self.log, self.args
            )
            self.assertEqual(mockobj.call_count, 0)


class TestConfig(TestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "growpart"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestConfig")
        self.args = []

        self.cloud_init = None
        self.handle = cc_growpart.handle
        self.tmppath = "/tmp/cloudinit-test-file"
        self.tmpdir = os.scandir("/tmp")
        self.tmpfile = open(self.tmppath, "w")

    def tearDown(self):
        self.tmpfile.close()
        os.remove(self.tmppath)

    @mock.patch.dict("os.environ", clear=True)
    def test_no_resizers_auto_is_fine(self):
        with mock.patch.object(
            subp, "subp", return_value=(HELP_GROWPART_NO_RESIZE, "")
        ) as mockobj:

            config = {"growpart": {"mode": "auto"}}
            self.handle(
                self.name, config, self.cloud_init, self.log, self.args
            )

            mockobj.assert_has_calls(
                [
                    mock.call(["growpart", "--help"], env={"LANG": "C"}),
                    mock.call(
                        ["gpart", "help"], env={"LANG": "C"}, rcs=[0, 1]
                    ),
                ]
            )

    @mock.patch.dict("os.environ", clear=True)
    def test_no_resizers_mode_growpart_is_exception(self):
        with mock.patch.object(
            subp, "subp", return_value=(HELP_GROWPART_NO_RESIZE, "")
        ) as mockobj:
            config = {"growpart": {"mode": "growpart"}}
            self.assertRaises(
                ValueError,
                self.handle,
                self.name,
                config,
                self.cloud_init,
                self.log,
                self.args,
            )

            mockobj.assert_called_once_with(
                ["growpart", "--help"], env={"LANG": "C"}
            )

    @mock.patch.dict("os.environ", clear=True)
    def test_mode_auto_prefers_growpart(self):
        with mock.patch.object(
            subp, "subp", return_value=(HELP_GROWPART_RESIZE, "")
        ) as mockobj:
            ret = cc_growpart.resizer_factory(mode="auto")
            self.assertIsInstance(ret, cc_growpart.ResizeGrowPart)

            mockobj.assert_called_once_with(
                ["growpart", "--help"], env={"LANG": "C"}
            )

    @mock.patch.dict("os.environ", {"LANG": "cs_CZ.UTF-8"}, clear=True)
    @mock.patch.object(temp_utils, "mkdtemp", return_value="/tmp/much-random")
    @mock.patch.object(stat, "S_ISDIR", return_value=False)
    @mock.patch.object(os.path, "samestat", return_value=True)
    @mock.patch.object(os.path, "join", return_value="/tmp")
    @mock.patch.object(os, "scandir", return_value=Scanner())
    @mock.patch.object(os, "mkdir")
    @mock.patch.object(os, "unlink")
    @mock.patch.object(os, "rmdir")
    @mock.patch.object(os, "open", return_value=1)
    @mock.patch.object(os, "close")
    @mock.patch.object(shutil, "rmtree")
    @mock.patch.object(os, "lseek", return_value=1024)
    @mock.patch.object(os, "lstat", return_value="interesting metadata")
    def test_force_lang_check_tempfile(self, *args, **kwargs):
        with mock.patch.object(
            subp, "subp", return_value=(HELP_GROWPART_RESIZE, "")
        ) as mockobj:

            ret = cc_growpart.resizer_factory(mode="auto")
            self.assertIsInstance(ret, cc_growpart.ResizeGrowPart)
            diskdev = "/dev/sdb"
            partnum = 1
            partdev = "/dev/sdb"
            ret.resize(diskdev, partnum, partdev)
        mockobj.assert_has_calls(
            [
                mock.call(
                    ["growpart", "--dry-run", diskdev, partnum],
                    env={"LANG": "C", "TMPDIR": "/tmp"},
                ),
                mock.call(
                    ["growpart", diskdev, partnum],
                    env={"LANG": "C", "TMPDIR": "/tmp"},
                ),
            ]
        )

    @mock.patch.dict("os.environ", {"LANG": "cs_CZ.UTF-8"}, clear=True)
    def test_mode_auto_falls_back_to_gpart(self):
        with mock.patch.object(
            subp, "subp", return_value=("", HELP_GPART)
        ) as mockobj:
            ret = cc_growpart.resizer_factory(mode="auto")
            self.assertIsInstance(ret, cc_growpart.ResizeGpart)

            mockobj.assert_has_calls(
                [
                    mock.call(["growpart", "--help"], env={"LANG": "C"}),
                    mock.call(
                        ["gpart", "help"], env={"LANG": "C"}, rcs=[0, 1]
                    ),
                ]
            )

    def test_handle_with_no_growpart_entry(self):
        # if no 'growpart' entry in config, then mode=auto should be used

        myresizer = object()
        retval = (
            (
                "/",
                cc_growpart.RESIZE.CHANGED,
                "my-message",
            ),
        )

        with ExitStack() as mocks:
            factory = mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "resizer_factory", return_value=myresizer
                )
            )
            rsdevs = mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "resize_devices", return_value=retval
                )
            )
            mocks.enter_context(
                mock.patch.object(
                    cc_growpart, "RESIZERS", (("mysizer", object),)
                )
            )

            self.handle(self.name, {}, self.cloud_init, self.log, self.args)

            factory.assert_called_once_with("auto")
            rsdevs.assert_called_once_with(myresizer, ["/"])


class TestResize(unittest.TestCase):
    def setUp(self):
        super(TestResize, self).setUp()
        self.name = "growpart"
        self.log = logging.getLogger("TestResize")

    def test_simple_devices(self):
        # test simple device list
        # this patches out devent2dev, os.stat, and device_part_info
        # so in the end, doesn't test a lot
        devs = ["/dev/XXda1", "/dev/YYda2"]
        devstat_ret = Bunch(
            st_mode=25008,
            st_ino=6078,
            st_dev=5,
            st_nlink=1,
            st_uid=0,
            st_gid=6,
            st_size=0,
            st_atime=0,
            st_mtime=0,
            st_ctime=0,
        )
        enoent = ["/dev/NOENT"]
        real_stat = os.stat
        resize_calls = []

        class myresizer(object):
            def resize(self, diskdev, partnum, partdev):
                resize_calls.append((diskdev, partnum, partdev))
                if partdev == "/dev/YYda2":
                    return (1024, 2048)
                return (1024, 1024)  # old size, new size

        def mystat(path):
            if path in devs:
                return devstat_ret
            if path in enoent:
                e = OSError("%s: does not exist" % path)
                e.errno = errno.ENOENT
                raise e
            return real_stat(path)

        try:
            opinfo = cc_growpart.device_part_info
            cc_growpart.device_part_info = simple_device_part_info
            os.stat = mystat

            resized = cc_growpart.resize_devices(myresizer(), devs + enoent)

            def find(name, res):
                for f in res:
                    if f[0] == name:
                        return f
                return None

            self.assertEqual(
                cc_growpart.RESIZE.NOCHANGE, find("/dev/XXda1", resized)[1]
            )
            self.assertEqual(
                cc_growpart.RESIZE.CHANGED, find("/dev/YYda2", resized)[1]
            )
            self.assertEqual(
                cc_growpart.RESIZE.SKIPPED, find(enoent[0], resized)[1]
            )
            # self.assertEqual(resize_calls,
            #                 [("/dev/XXda", "1", "/dev/XXda1"),
            #                  ("/dev/YYda", "2", "/dev/YYda2")])
        finally:
            cc_growpart.device_part_info = opinfo
            os.stat = real_stat


def simple_device_part_info(devpath):
    # simple stupid return (/dev/vda, 1) for /dev/vda
    ret = re.search("([^0-9]*)([0-9]*)$", devpath)
    x = (ret.group(1), ret.group(2))
    return x


class Bunch(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


# vi: ts=4 expandtab
