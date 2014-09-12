from mocker import MockerTestCase

from cloudinit import cloud
from cloudinit import util

from cloudinit.config import cc_growpart

import errno
import logging
import os
import re

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


class TestDisabled(MockerTestCase):
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
        self.mocker.replace(cc_growpart.resizer_factory,
                            passthrough=False)
        self.mocker.replay()

        self.handle(self.name, config, self.cloud_init, self.log, self.args)


class TestConfig(MockerTestCase):
    def setUp(self):
        super(TestConfig, self).setUp()
        self.name = "growpart"
        self.paths = None
        self.cloud = cloud.Cloud(None, self.paths, None, None, None)
        self.log = logging.getLogger("TestConfig")
        self.args = []
        os.environ = {}

        self.cloud_init = None
        self.handle = cc_growpart.handle

        # Order must be correct
        self.mocker.order()

    def test_no_resizers_auto_is_fine(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['growpart', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_GROWPART_NO_RESIZE, ""))
        self.mocker.replay()

        config = {'growpart': {'mode': 'auto'}}
        self.handle(self.name, config, self.cloud_init, self.log, self.args)

    def test_no_resizers_mode_growpart_is_exception(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['growpart', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_GROWPART_NO_RESIZE, ""))
        self.mocker.replay()

        config = {'growpart': {'mode': "growpart"}}
        self.assertRaises(ValueError, self.handle, self.name, config,
                          self.cloud_init, self.log, self.args)

    def test_mode_auto_prefers_growpart(self):
        subp = self.mocker.replace(util.subp, passthrough=False)
        subp(['growpart', '--help'], env={'LANG': 'C'})
        self.mocker.result((HELP_GROWPART_RESIZE, ""))
        self.mocker.replay()

        ret = cc_growpart.resizer_factory(mode="auto")
        self.assertTrue(isinstance(ret, cc_growpart.ResizeGrowPart))

    def test_handle_with_no_growpart_entry(self):
        # if no 'growpart' entry in config, then mode=auto should be used

        myresizer = object()

        factory = self.mocker.replace(cc_growpart.resizer_factory,
                                      passthrough=False)
        rsdevs = self.mocker.replace(cc_growpart.resize_devices,
                                     passthrough=False)
        factory("auto")
        self.mocker.result(myresizer)
        rsdevs(myresizer, ["/"])
        self.mocker.result((("/", cc_growpart.RESIZE.CHANGED, "my-message",),))
        self.mocker.replay()

        try:
            orig_resizers = cc_growpart.RESIZERS
            cc_growpart.RESIZERS = (('mysizer', object),)
            self.handle(self.name, {}, self.cloud_init, self.log, self.args)
        finally:
            cc_growpart.RESIZERS = orig_resizers


class TestResize(MockerTestCase):
    def setUp(self):
        super(TestResize, self).setUp()
        self.name = "growpart"
        self.log = logging.getLogger("TestResize")

        # Order must be correct
        self.mocker.order()

    def test_simple_devices(self):
        # test simple device list
        # this patches out devent2dev, os.stat, and device_part_info
        # so in the end, doesn't test a lot
        devs = ["/dev/XXda1", "/dev/YYda2"]
        devstat_ret = Bunch(st_mode=25008, st_ino=6078, st_dev=5L,
                            st_nlink=1, st_uid=0, st_gid=6, st_size=0,
                            st_atime=0, st_mtime=0, st_ctime=0)
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

            self.assertEqual(cc_growpart.RESIZE.NOCHANGE,
                             find("/dev/XXda1", resized)[1])
            self.assertEqual(cc_growpart.RESIZE.CHANGED,
                             find("/dev/YYda2", resized)[1])
            self.assertEqual(cc_growpart.RESIZE.SKIPPED,
                             find(enoent[0], resized)[1])
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
