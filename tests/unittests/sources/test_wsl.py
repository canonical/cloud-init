# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from copy import deepcopy

from cloudinit import util
from cloudinit.sources import DataSourceWSL as wsl
from tests.unittests.helpers import CiTestCase, mock

INSTANCE_NAME = "Noble-MLKit"
GOOD_MOUNTS = {
    "none": {
        "fstype": "tmpfs",
        "mountpoint": "/mnt/wsl",
        "opts": "rw,relatime",
    },
    "/dev/sdd": {
        "fstype": "ext4",
        "mountpoint": "/",
        "opts": "rw,relatime,...",
    },
    "sysfs": {
        "fstype": "sysfs",
        "mountpoint": "/sys",
        "opts": "rw,nosuid...",
    },
    "C:\\": {
        "fstype": "9p",
        "mountpoint": "/mnt/c",
        "opts": "rw,noatime,dirsync,aname=drvfs;path=C:\\;...",
    },
    "D:\\": {
        "fstype": "9p",
        "mountpoint": "/mnt/d",
        "opts": "rw,noatime,dirsync,aname=drvfs;path=D:\\;...",
    },
    "hugetblfs": {
        "fstype": "hugetblfs",
        "mountpoint": "/dev/hugepages",
        "opts": "rw,relatime...",
    },
}


class TestWSLHelperFunctions(CiTestCase):
    @mock.patch("cloudinit.util.subp.subp")
    def test_instance_name(self, m_subp):
        m_subp.return_value = util.subp.SubpResult(
            "//wsl.localhost/%s/" % (INSTANCE_NAME), ""
        )

        inst = wsl.instance_name()

        self.assertEqual(INSTANCE_NAME, inst)

    @mock.patch("cloudinit.util.mounts")
    def test_mounted_drives(self, m_mounts):
        # A good output
        m_mounts.return_value = deepcopy(GOOD_MOUNTS)
        mounts = wsl.mounted_win_drives()
        self.assertListEqual(["/mnt/c", "/mnt/d"], mounts)

        # no more drvfs in C:\ options
        m_mounts.return_value["C:\\"]["opts"] = "rw,relatime..."
        mounts = wsl.mounted_win_drives()
        self.assertListEqual(["/mnt/d"], mounts)

        # fstype mismatch for D:\
        m_mounts.return_value["D:\\"]["fstype"] = "zfs"
        mounts = wsl.mounted_win_drives()
        self.assertListEqual([], mounts)

    @mock.patch("cloudinit.util.subp.subp")
    def test_path_2_wsl_logic(self, m_subp):
        """
        Validates that we interpret stderr correctly when translating paths
        from Windows into Linux.
        """
        m_subp.return_value = util.subp.SubpResult("/mnt/c/ProgramData/", "")

        translated = wsl.win_path_2_wsl("C:\\ProgramData")
        self.assertIsNotNone(translated)

        # When an invalid drive is passed, wslpath prints the following pattern
        # to stderr:
        # wslpath: <ARGV_1 (aka the path)>
        m_subp.return_value = util.subp.SubpResult(
            "", "wslpath: X:\\ProgramData\\"
        )

        translated = wsl.win_path_2_wsl("X:\\ProgramData")
        self.assertIsNone(translated)

    @mock.patch("os.access")
    @mock.patch("cloudinit.util.mounts")
    def test_cmd_exe_ok(self, m_mounts, m_os_access):
        """
        Validates the happy path, when we find the Windows system drive and
        cmd.exe is executable.
        """
        m_mounts.return_value = deepcopy(GOOD_MOUNTS)
        m_os_access.return_value = True
        cmd = wsl.cmd_executable()
        # To please pyright not to complain about optional member access.
        assert cmd is not None
        self.assertIsNotNone(
            cmd.relative_to(GOOD_MOUNTS["C:\\"]["mountpoint"])
        )

    @mock.patch("os.access")
    @mock.patch("cloudinit.util.mounts")
    def test_cmd_not_executable(self, m_mounts, m_os_access):
        """
        When the cmd.exe found is not executable, then RuntimeError is raised.
        """
        m_mounts.return_value = deepcopy(GOOD_MOUNTS)
        m_os_access.return_value = True
        cmd = wsl.cmd_executable()
        # To please pyright not to complain about optional member access.
        assert cmd is not None
        self.assertIsNotNone(
            cmd.relative_to(GOOD_MOUNTS["C:\\"]["mountpoint"])
        )

        m_os_access.return_value = False
        self.assertIsNone(wsl.cmd_executable())

    @mock.patch("os.access")
    @mock.patch("cloudinit.util.mounts")
    def test_cmd_exe_no_win_mounts(self, m_mounts, m_os_access):
        """
        When no Windows drives are found, then RuntimeError is raised.
        """
        m_os_access.return_value = True

        m_mounts.return_value = deepcopy(GOOD_MOUNTS)
        m_mounts.return_value.pop("C:\\")
        m_mounts.return_value.pop("D:\\")
        with self.assertRaises(RuntimeError) as ctx:
            _ = wsl.cmd_executable()

        self.assertIn("drives", str(ctx.exception))
