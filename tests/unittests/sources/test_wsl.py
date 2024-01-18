# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
from copy import deepcopy
from email.mime.multipart import MIMEMultipart
from typing import cast

from cloudinit import helpers, util
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
SAMPLE_LSB = {
    "id": "Ubuntu",
    "description": "Ubuntu 24.04",
    "release": "24.04",
    "codename": "noble",
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
        self.assertIsNone(wsl.cmd_executable())

    @mock.patch("cloudinit.util.lsb_release")
    def test_candidate_files(self, m_lsb):
        """
        Validate the file names candidate for holding user-data and their
        order of precedence.
        """
        m_lsb.return_value = SAMPLE_LSB
        self.assertListEqual(
            [
                "%s.user-data" % INSTANCE_NAME,
                "Ubuntu-noble.user-data",
                "Ubuntu-all.user-data",
                "config.user-data",
            ],
            wsl.candidate_user_data_file_names(INSTANCE_NAME),
        )


SAMPLE_CFG = {"datasource_list": ["NoCloud", "WSL"]}


def join_payloads_from_content_type(
    part: MIMEMultipart, content_type: str
) -> str:
    """
    Helper function to decode and join all parts of a multipart MIME
    message matched by the content type.
    """
    content = ""
    for p in part.walk():
        if p.get_content_type() == content_type:
            content = content + str(p.get_payload(decode=True))

    return content


class TestWSLDataSource(CiTestCase):
    def setUp(self):
        super(TestWSLDataSource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {"cloud_dir": self.tmp, "run_dir": self.tmp}
        )

    @mock.patch("cloudinit.util.wait_for_files")
    @mock.patch("cloudinit.util.load_file")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.win_user_profile_dir")
    def test_metadata_id(self, m_prof_dir, m_iname, m_load_file, m_wait_file):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        m_wait_file.return_value = set()
        NICE_MACHINE_ID = "A-Nice-Machine-ID_by_systemd"
        m_load_file.return_value = NICE_MACHINE_ID
        m_iname.return_value = INSTANCE_NAME
        m_prof_dir.return_value = None

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )
        ds.get_data()

        self.assertEqual(
            ds.get_instance_id(),
            "%s-%s" % (INSTANCE_NAME, NICE_MACHINE_ID),
        )

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.win_user_profile_dir")
    def test_get_data_cc(self, m_prof_dir, m_iname, m_lsb):
        m_lsb.return_value = SAMPLE_LSB
        m_iname.return_value = INSTANCE_NAME
        m_prof_dir.return_value = self.tmp
        userdata_file = os.path.join(
            self.tmp, ".cloud-init", "%s.user-data" % INSTANCE_NAME
        )
        util.write_file(
            userdata_file, "#cloud-config\nwrite_files:\n- path: /etc/wsl.conf"
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )

        self.assertTrue(ds.get_data())
        ud = ds.get_userdata()

        self.assertIsNotNone(ud)
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        self.assertIsNotNone(userdata)
        self.assertIn("wsl.conf", cast(str, userdata))

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.win_user_profile_dir")
    def test_get_data_sh(self, m_prof_dir, m_iname, m_lsb):
        m_lsb.return_value = SAMPLE_LSB
        m_iname.return_value = INSTANCE_NAME
        m_prof_dir.return_value = self.tmp
        userdata_file = os.path.join(
            self.tmp, ".cloud-init", "%s.user-data" % INSTANCE_NAME
        )
        COMMAND = "echo Hello cloud-init on WSL!"
        util.write_file(userdata_file, "#!/bin/sh\n%s\n" % COMMAND)

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )

        self.assertTrue(ds.get_data())
        ud = ds.get_userdata()

        self.assertIsNotNone(ud)
        userdata = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/x-shellscript"
            ),
        )
        self.assertIn(COMMAND, userdata)

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.win_user_profile_dir")
    def test_data_precendence(self, m_prof_dir, m_iname, m_lsb):
        m_lsb.return_value = SAMPLE_LSB
        m_iname.return_value = INSTANCE_NAME
        m_prof_dir.return_value = self.tmp
        # This is the most specific: should win over the other user-data files.
        userdata_file = os.path.join(
            self.tmp, ".cloud-init", "Ubuntu-noble.user-data"
        )
        util.write_file(
            userdata_file, "#cloud-config\nwrite_files:\n- path: /etc/wsl.conf"
        )

        distro_file = os.path.join(
            self.tmp, ".cloud-init", "Ubuntu-all.user-data"
        )
        util.write_file(distro_file, "#!/bin/sh\n\necho Hello World\n")

        generic_file = os.path.join(
            self.tmp, ".cloud-init", "config.user-data"
        )
        util.write_file(generic_file, "#cloud-config\npackages:\n- g++-13\n")

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )

        self.assertTrue(ds.get_data())
        ud = ds.get_userdata()

        self.assertIsNotNone(ud)
        userdata = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/cloud-config"
            ),
        )
        self.assertIn("wsl.conf", userdata)
        self.assertNotIn("packages", userdata)
        shell_script = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/x-shellscript"
            ),
        )

        self.assertEqual("", shell_script)
