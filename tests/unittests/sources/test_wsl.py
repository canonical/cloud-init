# Copyright (C) 2024 Canonical Ltd.
#
# Author: Carlos Nihelton <carlos.santanadeoliveira@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
import logging
import os
import re
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

AGENT_SAMPLE = """\
#cloud-config
landscape:
    host:
        url: landscape.canonical.com:6554
    client:
        account_name: agenttest
        url: https://landscape.canonical.com/message-system
        ping_url: https://landscape.canonical.com/ping
        tags: wsl
ubuntu_pro:
    token: testtoken
"""

LANDSCAPE_SAMPLE = """\
#cloud-config
landscape:
  client:
    account_name: landscapetest
    tags: tag_aiml,tag_dev
locale: en_GB.UTF-8
"""


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
        "md_content,is_from_pro,raises,errors,warnings,md_expected",
        (
            pytest.param(
                None,
                False,
                does_not_raise(),
                [],
                [],
                {"instance-id": "iid-datasource-wsl"},
                id="default_md_on_no_md_file",
            ),
            pytest.param(
                '{"instance-id":"iid-load-from-pro"}',
                True,
                does_not_raise(),
                [],
                [],
                {"instance-id": "iid-load-from-pro"},
                id="metadata_from_pro",
            ),
            pytest.param(
                "{}",
                False,
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
                True,
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
        self,
        md_content,
        is_from_pro,
        raises,
        errors,
        warnings,
        md_expected,
        tmpdir,
        caplog,
    ):
        """meta-data file is optional. Errors are raised on invalid content."""
        path = ".cloud-init"
        if is_from_pro:
            path = ".ubuntupro/.cloud-init"

        if md_content is not None:
            dir = tmpdir.join(path)
            os.makedirs(dir)
            dir.join("myinstance.meta-data").write(md_content)
        with caplog.at_level(logging.WARNING):
            with raises:
                assert md_expected == wsl.load_instance_metadata(
                    tmpdir, "myinstance"
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
            content = content + str(p.get_payload())

    return content


class TestMergeAgentLandscapeData:
    @pytest.mark.parametrize(
        "agent_yaml,landscape_user_data,expected",
        (
            pytest.param(
                None, None, None, id="none_when_both_agent_and_ud_none"
            ),
            pytest.param(
                None, "", None, id="none_when_agent_none_and_ud_empty"
            ),
            pytest.param(
                "", None, None, id="none_when_agent_empty_and_ud_none"
            ),
            pytest.param("", "", None, id="none_when_both_agent_and_ud_empty"),
            pytest.param(
                AGENT_SAMPLE, "", AGENT_SAMPLE, id="agent_only_when_ud_empty"
            ),
            pytest.param(
                "",
                LANDSCAPE_SAMPLE,
                LANDSCAPE_SAMPLE,
                id="ud_only_when_agent_empty",
            ),
            pytest.param(
                "#cloud-config\nlandscape:\n client: {account_name: agent}\n",
                LANDSCAPE_SAMPLE,
                "#cloud-config\n# WSL datasouce Merged agent.yaml and "
                "user_data\n"
                + "\n".join(LANDSCAPE_SAMPLE.splitlines()[1:]).replace(
                    "landscapetest", "agent"
                ),
                id="merge_agent_and_landscape_ud_when_both_present",
            ),
        ),
    )
    def test_merged_data_excludes_empty_or_none(
        self, agent_yaml, landscape_user_data, expected, tmpdir
    ):
        agent_data = user_data = None
        if agent_yaml is not None:
            agent_path = tmpdir.join("agent.yaml")
            agent_path.write(agent_yaml)
            agent_data = wsl.ConfigData(agent_path, "")
        if landscape_user_data is not None:
            landscape_ud_path = tmpdir.join("instance_name.user_data")
            landscape_ud_path.write(landscape_user_data)
            user_data = wsl.ConfigData(landscape_ud_path, "")
        assert expected == wsl.merge_agent_landscape_data(
            agent_data, user_data
        )


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
        assert "wsl.conf" in userdata

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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/x-shellscript"
        )
        assert COMMAND in userdata

    @mock.patch("cloudinit.util.lsb_release")
    def test_get_data_jinja(self, m_lsb_release, paths, tmpdir):
        """Assert we don't mistakenly treat jinja as final cloud-config"""
        m_lsb_release.return_value = SAMPLE_LINUX_DISTRO
        data_path = tmpdir.join(".cloud-init", f"{INSTANCE_NAME}.user-data")
        data_path.dirpath().mkdir()
        data_path.write(
            """## template: jinja
#cloud-config
write_files:
- path: /etc/{{ v1.instance_name }}.conf
"""
        )

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )

        assert ds.get_data() is True
        ud = ds.get_userdata(True)
        print(ud)

        assert ud is not None
        assert "write_files" in join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/jinja2"
        ), "Jinja should not be treated as final cloud-config"
        assert "write_files" not in join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        ), "No cloud-config part should exist"

    @pytest.mark.parametrize("with_agent_data", [True, False])
    @mock.patch("cloudinit.util.lsb_release")
    def test_get_data_x(
        self, m_lsb_release, with_agent_data, caplog, paths, tmpdir
    ):
        """
        Assert behavior of empty .cloud-config dir with and without agent data
        """
        m_lsb_release.return_value = SAMPLE_LINUX_DISTRO
        data_path = tmpdir.join(".cloud-init", f"{INSTANCE_NAME}.user-data")
        data_path.dirpath().mkdir()

        if with_agent_data:
            ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
            os.makedirs(ubuntu_pro_tmp, exist_ok=True)
            agent_path = ubuntu_pro_tmp.join("agent.yaml")
            agent_path.write(AGENT_SAMPLE)

        ds = wsl.DataSourceWSL(
            sys_cfg=SAMPLE_CFG,
            distro=_get_distro("ubuntu"),
            paths=paths,
        )

        assert ds.get_data() is with_agent_data
        if with_agent_data:
            assert ds.userdata_raw == AGENT_SAMPLE
        else:
            assert ds.userdata_raw is None

        expected_log_level = logging.INFO if with_agent_data else logging.ERROR
        regex = (
            "Unable to load any user-data file in /[^:]*/.cloud-init:"
            " /.*/.cloud-init directory is empty"
        )
        messages = [
            x.message
            for x in caplog.records
            if x.levelno == expected_log_level and re.match(regex, x.message)
        ]
        assert (
            len(messages) > 0
        ), "Expected log message matching '{}' with log level '{}'".format(
            regex, expected_log_level
        )

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_data_precedence(self, m_get_linux_dist, tmpdir, paths):
        """Validates the precedence of user-data files."""

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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        assert "wsl.conf" in userdata
        assert "packages" not in userdata
        shell_script = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/x-shellscript"
        )

        assert "" == shell_script

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_interaction_with_pro(self, m_get_linux_dist, tmpdir, paths):
        """Validates the interaction of user-data and Pro For WSL agent data"""

        m_get_linux_dist.return_value = ("ubuntu", "25.10", "plucky")

        user_file = tmpdir.join(".cloud-init", "ubuntu-25.10.user-data")
        user_file.dirpath().mkdir()
        user_file.write("#cloud-config\nwrite_files:\n- path: /etc/wsl.conf")

        # The winner should be the merge of the agent and user provided data.
        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    host:
        url: landscape.canonical.com:6554
    client:
        account_name: agenttest
        url: https://landscape.canonical.com/message-system
        ping_url: https://landscape.canonical.com/ping
        tags: wsl
ubuntu_pro:
    token: testtoken"""
        )
        SAMPLE_ID = "Nice-ID"
        agent_metadata_path = ubuntu_pro_tmp.join(f"{INSTANCE_NAME}.meta-data")
        agent_metadata_path.write(
            f'{{"instance-id":"{SAMPLE_ID}"}}',
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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        assert "wsl.conf" in userdata
        assert "packages" not in userdata
        assert "ubuntu_pro" in userdata
        assert "landscape" in userdata
        assert "agenttest" in userdata
        assert "installation_request_id" in userdata
        assert SAMPLE_ID in userdata

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_landscape_vs_local_user(self, m_get_linux_dist, tmpdir, paths):
        """Validates the precendence of Landscape-provided over local data"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        user_file = tmpdir.join(".cloud-init", "ubuntu-24.04.user-data")
        user_file.dirpath().mkdir()
        user_file.write(
            """#cloud-config
ubuntu_pro:
    token: usertoken
package_update: true"""
        )

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)
        landscape_file = ubuntu_pro_tmp.join("%s.user-data" % INSTANCE_NAME)
        landscape_file.write(LANDSCAPE_SAMPLE)

        # Run the datasource
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

        assert (
            "locale" in userdata
            and "landscapetest" in userdata
            and "ubuntu_pro" not in userdata
            and "package_update" not in userdata
        ), "Landscape data should have overriden user provided data"

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_landscape_provided_data(self, m_get_linux_dist, tmpdir, paths):
        """Validates the interaction of Pro For WSL agent and Landscape data"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    host:
        url: hosted.com:6554
    client:
        account_name: agenttest
        url: https://hosted.com/message-system
        ping_url: https://hosted.com/ping
        ssl_public_key: C:\\Users\\User\\server.pem
        tags: wsl
ubuntu_pro:
    token: testtoken"""
        )

        landscape_file = ubuntu_pro_tmp.join("%s.user-data" % INSTANCE_NAME)
        landscape_file.write(
            """#cloud-config
landscape:
  client:
    account_name: landscapetest
    tags: tag_aiml,tag_dev
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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )

        assert "ubuntu_pro" in userdata, "Agent data should be present"
        assert "package_update" in userdata, (
            "package_update entry should not be overriden by agent data"
            " nor ignored"
        )
        assert (
            "landscapetest" not in userdata and "agenttest" in userdata
        ), "Landscape account name should have been overriden by agent data"
        # Make sure we have tags from Landscape data, not agent's
        assert (
            "tag_aiml" in userdata and "tag_dev" in userdata
        ), "User-data should override agent data's Landscape computer tags"
        assert "wsl" not in userdata

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_landscape_empty_data(self, m_get_linux_dist, tmpdir, paths):
        """Asserts that Pro for WSL data is present when Landscape is empty"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    host:
        url: hosted.com:6554
    client:
        account_name: agent_test
        url: https://hosted.com/message-system
        ping_url: https://hosted.com/ping
        ssl_public_key: C:\\Users\\User\\server.pem
        tags: wsl
ubuntu_pro:
    token: agent_token"""
        )

        landscape_file = ubuntu_pro_tmp.join("%s.user-data" % INSTANCE_NAME)
        landscape_file.write("")

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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )

        assert (
            "agent_test" in userdata and "agent_token" in userdata
        ), "Agent data should be present"

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_landscape_shell_script(self, m_get_linux_dist, tmpdir, paths):
        """Asserts that Pro for WSL and Landscape goes multipart"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    host:
        url: hosted.com:6554
    client:
        account_name: agent_test
        url: https://hosted.com/message-system
        ping_url: https://hosted.com/ping
        ssl_public_key: C:\\Users\\User\\server.pem
        tags: wsl
ubuntu_pro:
    token: agent_token"""
        )

        COMMAND = "echo Hello cloud-init on WSL!"
        landscape_file = ubuntu_pro_tmp.join("%s.user-data" % INSTANCE_NAME)
        landscape_file.write(f"#!/bin/sh\n{COMMAND}\n")

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
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )

        assert (
            "agent_test" in userdata and "agent_token" in userdata
        ), "Agent data should be present"

        shell_script = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/x-shellscript"
        )

        assert COMMAND in shell_script

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_with_landscape_no_tags(self, m_get_linux_dist, tmpdir, paths):
        """Validates the Pro For WSL default Landscape tags are applied"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        agent_file.write(
            """#cloud-config
landscape:
    host:
        url: landscape.canonical.com:6554
    client:
        account_name: agenttest
        url: https://landscape.canonical.com/message-system
        ping_url: https://landscape.canonical.com/ping
        tags: wsl
ubuntu_pro:
    token: testtoken"""
        )
        # Set up some Landscape provided user data without tags
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

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )

        assert (
            "tags: wsl" in userdata
        ), "Landscape computer tags should match UP4W agent's data defaults"

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_with_no_tags_at_all(self, m_get_linux_dist, tmpdir, paths):
        """Asserts the DS still works if there are no Landscape tags at all"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO

        user_file = tmpdir.join(".cloud-init", "ubuntu-24.04.user-data")
        user_file.dirpath().mkdir()
        user_file.write("#cloud-config\nwrite_files:\n- path: /etc/wsl.conf")

        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        # Make sure we don't crash if there are no tags anywhere.
        agent_file.write(
            """#cloud-config
ubuntu_pro:
    token: up4w_token"""
        )
        # Set up some Landscape provided user data without tags
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

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        assert "landscapetest" in userdata
        assert "up4w_token" in userdata
        assert "tags" not in userdata

    @mock.patch("cloudinit.util.get_linux_distro")
    def test_with_no_client_subkey(self, m_get_linux_dist, tmpdir, paths):
        """Validates the DS works without the landscape.client subkey"""

        m_get_linux_dist.return_value = SAMPLE_LINUX_DISTRO
        ubuntu_pro_tmp = tmpdir.join(".ubuntupro", ".cloud-init")
        os.makedirs(ubuntu_pro_tmp, exist_ok=True)

        agent_file = ubuntu_pro_tmp.join("agent.yaml")
        # Make sure we don't crash if there is no client subkey.
        # (That would be a bug in the agent as there is no other config
        # value for landscape outside of landscape.client, so I'm making up
        # some non-sense keys just to make sure we won't crash)
        agent_file.write(
            """#cloud-config
landscape:
    server:
        port: 6554
ubuntu_pro:
    token: up4w_token"""
        )

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

        assert ds.get_data() is True
        ud = ds.get_userdata()

        assert ud is not None
        userdata = join_payloads_from_content_type(
            cast(MIMEMultipart, ud), "text/cloud-config"
        )
        assert "landscapetest" not in userdata
        assert (
            "port: 6554" in userdata
        ), "agent data should override the entire landscape config."

        assert "up4w_token" in userdata
