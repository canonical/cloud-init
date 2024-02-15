# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
from copy import deepcopy
from email.mime.multipart import MIMEMultipart
from pathlib import PurePath
from typing import cast

import pytest

from cloudinit import util
from cloudinit.sources import DataSourceWSL as wsl
from tests.unittests.helpers import does_not_raise, mock

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


class TestWSLHelperFunctions:
    @mock.patch("cloudinit.util.subp.subp")
    def test_instance_name(self, m_subp):
        m_subp.return_value = util.subp.SubpResult(
            f"//wsl.localhost/{INSTANCE_NAME}/", ""
        )

        assert INSTANCE_NAME == wsl.instance_name()

    @mock.patch("cloudinit.util.mounts")
    def test_mounted_drives(self, m_mounts):
        # A good output
        m_mounts.return_value = deepcopy(GOOD_MOUNTS)
        mounts = wsl.mounted_win_drives()
        assert ["/mnt/c", "/mnt/d"] == mounts

        # no more drvfs in C:\ options
        m_mounts.return_value["C:\\"]["opts"] = "rw,relatime..."
        mounts = wsl.mounted_win_drives()
        assert ["/mnt/d"] == mounts

        # fstype mismatch for D:\
        m_mounts.return_value["D:\\"]["fstype"] = "zfs"
        mounts = wsl.mounted_win_drives()
        assert [] == mounts

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
        assert None is not cmd.relative_to(GOOD_MOUNTS["C:\\"]["mountpoint"])

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
        assert None is not cmd.relative_to(GOOD_MOUNTS["C:\\"]["mountpoint"])

        m_os_access.return_value = False
        with pytest.raises(IOError):
            wsl.cmd_executable()

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
        with pytest.raises(IOError):
            wsl.cmd_executable()

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_candidate_files(self, m_gld):
        """
        Validate the file names candidate for holding user-data and their
        order of precedence.
        """
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        assert [
            f"{INSTANCE_NAME}.user-data",
            "ubuntu-24.04.user-data",
            "ubuntu-all.user-data",
            "default.user-data",
        ] == wsl.candidate_user_data_file_names(INSTANCE_NAME)

    @pytest.mark.parametrize(
        "md_content,raises,errors,warnings,md_expected",
        (
            pytest.param(
                None,
                does_not_raise(),
                [],
                [],
                {"instance-id": "iid-datasource-wsl"},
                id="default_md_on_no_md_file",
            ),
            pytest.param(
                "{}",
                pytest.raises(
                    ValueError,
                    match=(
                        "myinstance.meta-data does not contain instance-id key"
                    ),
                ),
                ["myinstance.meta-data does not contain instance-id key"],
                [],
                "",
                id="error_on_md_missing_instance_id_key",
            ),
            pytest.param(
                "{",
                pytest.raises(
                    ValueError,
                    match=(
                        "myinstance.meta-data does not contain instance-id key"
                    ),
                ),
                ["myinstance.meta-data does not contain instance-id key"],
                ["Failed loading yaml blob. Invalid format at line 1"],
                "",
                id="error_on_md_invalid_yaml",
            ),
        ),
    )
    def test_load_instance_metadata(
        self, md_content, raises, errors, warnings, md_expected, tmpdir, caplog
    ):
        """meta-data file is optional. Errors are raised on invalid content."""
        if md_content is not None:
            tmpdir.join("myinstance.meta-data").write(md_content)
        with caplog.at_level(logging.WARNING):
            with raises:
                assert md_expected == wsl.load_instance_metadata(
                    PurePath(tmpdir), "myinstance"
                )
            warning_logs = "\n".join(
                [
                    x.message
                    for x in caplog.records
                    if x.levelno == logging.WARNING
                ]
            )
            error_logs = "\n".join(
                [
                    x.message
                    for x in caplog.records
                    if x.levelno == logging.ERROR
                ]
            )
        if warnings:
            for warning in warnings:
                assert warning in warning_logs
        else:
            assert "" == warning_logs
        if errors:
            for error in errors:
                assert error in error_logs
        else:
            assert "" == error_logs


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


class TestWSLDataSource:
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_metadata_id_default(self, m_seed_dir, m_iname, tmpdir, paths):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(tmpdir)

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=paths,
        )
        ds.get_data()

        assert ds.get_instance_id() == wsl.DEFAULT_INSTANCE_ID

    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_metadata_id(self, m_seed_dir, m_iname, tmpdir, paths):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(tmpdir)
        SAMPLE_ID = "Nice-ID"
        tmpdir.join(f"{INSTANCE_NAME}.meta-data").write(
            f'{{"instance-id":"{SAMPLE_ID}"}}',
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=paths,
        )
        ds.get_data()

        assert ds.get_instance_id() == SAMPLE_ID

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_get_data_cc(self, m_seed_dir, m_iname, m_gld, paths, tmpdir):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(tmpdir)
        tmpdir.join(f"{INSTANCE_NAME}.user-data").write(
            "#cloud-config\nwrite_files:\n- path: /etc/wsl.conf"
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=paths,
        )

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        assert userdata is not None
        assert "wsl.conf" in cast(str, userdata)

    @mock.patch("cloudinit.util.lsb_release")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_get_data_sh(self, m_seed_dir, m_iname, m_gld, tmpdir, paths):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(tmpdir)
        COMMAND = "echo Hello cloud-init on WSL!"
        tmpdir.join(f"{INSTANCE_NAME}.user-data").write(
            f"#!/bin/sh\n{COMMAND}\n"
        )
        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=paths,
        )

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/x-shellscript"
            ),
        )
        assert COMMAND in userdata

    @mock.patch("cloudinit.util.get_linux_distro")
    @mock.patch("cloudinit.sources.DataSourceWSL.instance_name")
    @mock.patch("cloudinit.sources.DataSourceWSL.cloud_init_data_dir")
    def test_data_precedence(self, m_seed_dir, m_iname, m_gld, tmpdir, paths):
        m_gld.return_value = SAMPLE_LINUX_DISTRO
        m_iname.return_value = INSTANCE_NAME
        m_seed_dir.return_value = PurePath(tmpdir)
        # This is the most specific: should win over the other user-data files.
        # Also, notice the file name casing: should be irrelevant.
        tmpdir.join("ubuntu-24.04.user-data").write(
            "#cloud-config\nwrite_files:\n- path: /etc/wsl.conf"
        )

        distro_file = tmpdir.join(".cloud-init", "Ubuntu-all.user-data")
        distro_file.dirpath().mkdir()
        distro_file.write("#!/bin/sh\n\necho Hello World\n")

        generic_file = tmpdir.join(".cloud-init", "default.user-data")
        generic_file.write("#cloud-config\npackages:\n- g++-13\n")

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=None,
            paths=paths,
        )

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/cloud-config"
            ),
        )
        assert "wsl.conf" in userdata
        assert "packages" not in userdata
        shell_script = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/x-shellscript"
            ),
        )

        assert "" == shell_script
