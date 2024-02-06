# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
from copy import deepcopy
from email.mime.multipart import MIMEMultipart
from pathlib import PurePath
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
SAMPLE_LINUX_DISTRO = ("ubuntu", "24.04", "noble")


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
        self.assertRaises(IOError, wsl.cmd_executable)

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
        self.assertRaises(IOError, wsl.cmd_executable)

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_candidate_files(self, m_gld):
        """
        Validate the file names candidate for holding user-data and their
        order of precedence.
        """
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        self.assertListEqual(
            [
                "%s.user-data" % INSTANCE_NAME,
                "ubuntu-24.04.user-data",
                "ubuntu-all.user-data",
                "default.user-data",
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

    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_metadata_id_default(self, m_seed_dir, m_iname):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(self.tmp)

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )
        ds.get_data()

        self.assertEqual(ds.get_instance_id(), wsl.DEFAULT_INSTANCE_ID)

    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_metadata_id(self, m_seed_dir, m_iname):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(self.tmp)
        SAMPLE_ID = "Nice-ID"
        util.write_file(
            os.path.join(self.tmp, "%s.meta-data" % INSTANCE_NAME),
            '{"instance-id":"%s"}' % SAMPLE_ID,
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=self.paths,
        )
        ds.get_data()

        self.assertEqual(ds.get_instance_id(), SAMPLE_ID)

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_get_data_cc(self, m_seed_dir, m_iname, m_gld):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(self.tmp)
        userdata_file = os.path.join(
            self.tmp, "%s.user-data" % INSTANCE_NAME
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
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_get_data_sh(self, m_seed_dir, m_iname, m_gld):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(self.tmp)
        userdata_file = os.path.join(
            self.tmp, "%s.user-data" % INSTANCE_NAME
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

    @mock.patch("cloudinit.util.get_linux_distro")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_data_precedence(self, m_seed_dir, m_iname, m_gld):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(self.tmp)
        # This is the most specific: should win over the other user-data files.
        # Also, notice the file name casing: should be irrelevant.
        userdata_file = os.path.join(
            self.tmp, "ubuntu-24.04.user-data"
        )
        util.write_file(
            userdata_file, "#cloud-config\nwrite_files:\n- path: /etc/wsl.conf"
        )

        distro_file = os.path.join(
            self.tmp, ".cloud-init", "Ubuntu-all.user-data"
        )
        util.write_file(distro_file, "#!/bin/sh\n\necho Hello World\n")

        generic_file = os.path.join(
            self.tmp, ".cloud-init", "default.user-data"
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
