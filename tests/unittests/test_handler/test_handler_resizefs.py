# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.config import cc_resizefs

import textwrap
import unittest

try:
    from unittest import mock
except ImportError:
    import mock


class TestResizefs(unittest.TestCase):
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
        res = cc_resizefs.can_skip_resize(fs_type, resize_what, devpth)
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
        res = cc_resizefs.can_skip_resize(fs_type, resize_what, devpth)
        self.assertTrue(res)


# vi: ts=4 expandtab
