# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit.util import find_freebsd_part, get_path_dev_freebsd
from tests.unittests.helpers import CiTestCase, get_distro, mock

M_PATH = "cloudinit.distros.freebsd."


class TestFreeBSD:
    @mock.patch(M_PATH + "subp.subp")
    def test_add_user(self, m_subp):
        distro = get_distro("freebsd")
        assert True is distro.add_user("me2", uid=1234, default=False)
        assert [
            mock.call(
                [
                    "pw",
                    "useradd",
                    "-n",
                    "me2",
                    "-u",
                    "1234",
                    "-d/usr/home/me2",
                    "-m",
                ],
                logstring=[
                    "pw",
                    "useradd",
                    "-n",
                    "me2",
                    "-d/usr/home/me2",
                    "-m",
                ],
            )
        ] == m_subp.call_args_list

    def test_unlock_passwd(self, caplog):
        distro = get_distro("freebsd")
        distro.unlock_passwd("me2")
        assert (
            "Dragonfly BSD/FreeBSD password lock is not reversible, "
            "ignoring unlock for user me2" in caplog.text
        )


class TestDeviceLookUp(CiTestCase):
    @mock.patch("cloudinit.subp.subp")
    def test_find_freebsd_part_label(self, mock_subp):
        glabel_out = """
gptid/fa52d426-c337-11e6-8911-00155d4c5e47  N/A  da0p1
                              label/rootfs  N/A  da0p2
                                label/swap  N/A  da0p3
"""
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part("/dev/label/rootfs")
        self.assertEqual("da0p2", res)

    @mock.patch("cloudinit.subp.subp")
    def test_find_freebsd_part_gpt(self, mock_subp):
        glabel_out = """
                                gpt/bootfs  N/A  vtbd0p1
gptid/3f4cbe26-75da-11e8-a8f2-002590ec6166  N/A  vtbd0p1
                                gpt/swapfs  N/A  vtbd0p2
                                gpt/rootfs  N/A  vtbd0p3
                            iso9660/cidata  N/A  vtbd2
"""
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part("/dev/gpt/rootfs")
        self.assertEqual("vtbd0p3", res)

    @mock.patch("cloudinit.subp.subp")
    def test_find_freebsd_part_gptid(self, mock_subp):
        glabel_out = """
                                gpt/bootfs  N/A  vtbd0p1
                                gpt/efiesp  N/A  vtbd0p2
                                gpt/swapfs  N/A  vtbd0p3
gptid/4cd084b4-7fb4-11ee-a7ba-002590ec5bf2  N/A  vtbd0p4
"""
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part(
            "/dev/gptid/4cd084b4-7fb4-11ee-a7ba-002590ec5bf2"
        )
        self.assertEqual("vtbd0p4", res)

    @mock.patch("cloudinit.subp.subp")
    def test_find_freebsd_part_ufsid(self, mock_subp):
        glabel_out = """
                                gpt/bootfs  N/A  vtbd0p1
                                gpt/efiesp  N/A  vtbd0p2
                                gpt/swapfs  N/A  vtbd0p3
                    ufsid/654e0663786f5131  N/A  vtbd0p4
"""
        mock_subp.return_value = (glabel_out, "")
        res = find_freebsd_part("/dev/ufsid/654e0663786f5131")
        self.assertEqual("vtbd0p4", res)

    def test_get_path_dev_freebsd_label(self):
        mnt_list = """
/dev/label/rootfs  /                ufs     rw              1 1
devfs              /dev             devfs   rw,multilabel   0 0
fdescfs            /dev/fd          fdescfs rw              0 0
/dev/da1s1         /mnt/resource    ufs     rw              2 2
"""
        with mock.patch.object(os.path, "exists", return_value=True):
            res = get_path_dev_freebsd("/etc", mnt_list)
            self.assertIsNotNone(res)
