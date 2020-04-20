# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.util import (find_freebsd_part, get_path_dev_freebsd)
from cloudinit.tests.helpers import (CiTestCase, mock)

import os


class TestDeviceLookUp(CiTestCase):

    @mock.patch('cloudinit.util.subp')
    def test_find_freebsd_part_label(self, mock_subp):
        glabel_out = '''
gptid/fa52d426-c337-11e6-8911-00155d4c5e47  N/A  da0p1
                              label/rootfs  N/A  da0p2
                                label/swap  N/A  da0p3
'''
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part("/dev/label/rootfs")
        self.assertEqual("da0p2", res)

    @mock.patch('cloudinit.util.subp')
    def test_find_freebsd_part_gpt(self, mock_subp):
        glabel_out = '''
                                gpt/bootfs  N/A  vtbd0p1
gptid/3f4cbe26-75da-11e8-a8f2-002590ec6166  N/A  vtbd0p1
                                gpt/swapfs  N/A  vtbd0p2
                                gpt/rootfs  N/A  vtbd0p3
                            iso9660/cidata  N/A  vtbd2
'''
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part("/dev/gpt/rootfs")
        self.assertEqual("vtbd0p3", res)

    def test_get_path_dev_freebsd_label(self):
        mnt_list = '''
/dev/label/rootfs  /                ufs     rw              1 1
devfs              /dev             devfs   rw,multilabel   0 0
fdescfs            /dev/fd          fdescfs rw              0 0
/dev/da1s1         /mnt/resource    ufs     rw              2 2
'''
        with mock.patch.object(os.path, 'exists',
                               return_value=True):
            res = get_path_dev_freebsd('/etc', mnt_list)
            self.assertIsNotNone(res)
