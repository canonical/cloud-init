# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
from copy import deepcopy
from email.mime.multipart import MIMEMultipart
from pathlib import PurePath
from typing import cast

import pytest

from cloudinit import util
from cloudinit.sources import DataSourceWSL as wsl
from tests.unittests.distros import _get_distro
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
SAMPLE_LINUX_DISTRO_NO_VERSION_ID = ("debian", "", "trixie")


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

    @pytest.mark.parametrize(
        "linux_distro_value,files",
        (
            (
                SAMPLE_LINUX_DISTRO,
                [
                    f"{INSTANCE_NAME}.user-data",
                    "ubuntu-24.04.user-data",
                    "ubuntu-all.user-data",
                    "default.user-data",
                ],
            ),
            (
                SAMPLE_LINUX_DISTRO_NO_VERSION_ID,
                [
                    f"{INSTANCE_NAME}.user-data",
                    "debian-trixie.user-data",
                    "debian-all.user-data",
                    "default.user-data",
                ],
            ),
        ),
    )
    @mock.patch("cloudinit.util.get_linux_distro")
    def test_candidate_files(self, m_gld, linux_distro_value, files):
        """
        Validate the file names candidate for holding user-data and their
        order of precedence.
        """
        m_gld.return_value = linux_distro_value
        assert files == wsl.candidate_user_data_file_names(INSTANCE_NAME)

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
    @pytest.fixture(autouse=True)
    def setup(self, mocker, tmpdir):
        mocker.patch(
            "cloudinit.sources.DataSourceWSL.instance_name",
            return_value=INSTANCE_NAME,
        )
        mocker.patch(
            "cloudinit.sources.DataSourceWSL.find_home",
            return_value=PurePath(tmpdir),
        )
        mocker.patch(
            "cloudinit.sources.DataSourceWSL.subp.which",
            return_value="/usr/bin/wslpath",
        )

    def test_metadata_id_default(self, tmpdir, paths):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )
        ds.get_data()

        assert ds.get_instance_id() == wsl.DEFAULT_INSTANCE_ID

    def test_metadata_id(self, tmpdir, paths):
        """
        Validates that instance-id is properly set, indepedent of the existence
        of user-data.
        """
        SAMPLE_ID = "Nice-ID"
        metadata_path = tmpdir.join(
            ".cloud-init", f"{INSTANCE_NAME}.meta-data"
        )
        metadata_path.dirpath().mkdir()
        metadata_path.write(
            f'{{"instance-id":"{SAMPLE_ID}"}}',
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )
        ds.get_data()

        assert ds.get_instance_id() == SAMPLE_ID

    @mock.patch("cloudinit.util.lsb_release")
    def test_get_data_cc(self, m_lsb_release, paths, tmpdir):
        m_lsb_release.return_value = SAMPLE_LINUX_DISTRO
        data_path = tmpdir.join(".cloud-init", f"{INSTANCE_NAME}.user-data")
        data_path.dirpath().mkdir()
        data_path.write("#cloud-config\nwrite_files:\n- path: /etc/wsl.conf")

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
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
    def test_get_data_sh(self, m_lsb_release, tmpdir, paths):
        m_lsb_release.return_value = SAMPLE_LINUX_DISTRO
        COMMAND = "echo Hello cloud-init on WSL!"
        data_path = tmpdir.join(".cloud-init", f"{INSTANCE_NAME}.user-data")
        data_path.dirpath().mkdir()
        data_path.write(f"#!/bin/sh\n{COMMAND}\n")
        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
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
    def test_data_precedence(self, m_get_linux_dist, tmpdir, paths):
        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        # Set up basic user data:

        # This is the most specific: should win over the other user-data files.
        # Also, notice the file name casing: should be irrelevant.
        user_file = tmpdir.join(".cloud-init", "ubuntu-24.04.user-data")
        user_file.dirpath().mkdir()
        user_file.write("#cloud-config\nwrite_files:\n- path: /etc/wsl.conf")

        distro_file = tmpdir.join(".cloud-init", "Ubuntu-all.user-data")
        distro_file.write("#!/bin/sh\n\necho Hello World\n")

        generic_file = tmpdir.join(".cloud-init", "default.user-data")
        generic_file.write("#cloud-config\npackages:\n- g++-13\n")

        # Run the datasource
        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )

        # Assert user data is properly loaded
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

        # Additionally set up some UP4W agent data:

        # Now the winner should be the merge of the agent and Landscape data.
        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    client:
      account_name: agenttest
ubuntu_advantage:
    token: testtoken"""
        )

        # Run the datasource
        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )

        # Assert agent combines with existing user data
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
        assert "ubuntu_advantage" in userdata
        assert "landscape" in userdata
        assert "agenttest" in userdata

        # Additionally set up some Landscape provided user data
        landscape_file = ubuntu_pro_tmp.join("%s.user-data" % INSTANCE_NAME)
        landscape_file.write(
            """#cloud-config
landscape:
  client:
    account_name: landscapetest
package_update: true"""
        )

        # Run the datasource
        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )

        # Assert Landscape and Agent combine, with Agent taking precedence
        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = cast(
            str,
            join_payloads_from_content_type(
                cast(MIMEMultipart, ud), "text/cloud-config"
            ),
        )

        assert "wsl.conf" not in userdata
        assert "packages" not in userdata
        assert "ubuntu_advantage" in userdata
        assert "package_update" in userdata, (
            "package_update entry should not be overriden by agent data"
            " nor ignored"
        )
        assert "landscape" in userdata
        assert (
            "landscapetest" not in userdata and "agenttest" in userdata
        ), "Landscape account name should have been overriden by agent data"
