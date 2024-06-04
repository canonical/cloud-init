# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.util"""

import base64
import errno
import io
import json
import logging
import os
import platform
import re
import shutil
import stat
import tempfile
from collections import deque
from pathlib import Path
from textwrap import dedent
from unittest import mock
from urllib.parse import urlparse

import pytest
import yaml

from cloudinit import atomic_helper, features, importer, subp, url_helper, util
from cloudinit.distros import Distro
from cloudinit.helpers import Paths
from cloudinit.sources import DataSourceHostname
from cloudinit.subp import SubpResult
from tests.unittests import helpers
from tests.unittests.helpers import CiTestCase, skipIf, skipUnlessJinja

LOG = logging.getLogger(__name__)
M_PATH = "cloudinit.util."

MOUNT_INFO = [
    "68 0 8:3 / / ro,relatime shared:1 - btrfs /dev/sda1 ro,attr2,inode64",
    "153 68 254:0 / /home rw,relatime shared:101 - xfs /dev/sda2 rw,attr2",
]

OS_RELEASE_SLES = dedent(
    """\
    NAME="SLES"
    VERSION="12-SP3"
    VERSION_ID="12.3"
    PRETTY_NAME="SUSE Linux Enterprise Server 12 SP3"
    ID="sles"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:suse:sles:12:sp3"
"""
)

OS_RELEASE_OPENSUSE = dedent(
    """\
    NAME="openSUSE Leap"
    VERSION="42.3"
    ID=opensuse
    ID_LIKE="suse"
    VERSION_ID="42.3"
    PRETTY_NAME="openSUSE Leap 42.3"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:opensuse:leap:42.3"
    BUG_REPORT_URL="https://bugs.opensuse.org"
    HOME_URL="https://www.opensuse.org/"
"""
)

OS_RELEASE_OPENSUSE_L15 = dedent(
    """\
    NAME="openSUSE Leap"
    VERSION="15.0"
    ID="opensuse-leap"
    ID_LIKE="suse opensuse"
    VERSION_ID="15.0"
    PRETTY_NAME="openSUSE Leap 15.0"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:opensuse:leap:15.0"
    BUG_REPORT_URL="https://bugs.opensuse.org"
    HOME_URL="https://www.opensuse.org/"
"""
)

OS_RELEASE_OPENSUSE_TW = dedent(
    """\
    NAME="openSUSE Tumbleweed"
    ID="opensuse-tumbleweed"
    ID_LIKE="opensuse suse"
    VERSION_ID="20180920"
    PRETTY_NAME="openSUSE Tumbleweed"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:opensuse:tumbleweed:20180920"
    BUG_REPORT_URL="https://bugs.opensuse.org"
    HOME_URL="https://www.opensuse.org/"
"""
)

OS_RELEASE_CENTOS = dedent(
    """\
    NAME="CentOS Linux"
    VERSION="7 (Core)"
    ID="centos"
    ID_LIKE="rhel fedora"
    VERSION_ID="7"
    PRETTY_NAME="CentOS Linux 7 (Core)"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:centos:centos:7"
    HOME_URL="https://www.centos.org/"
    BUG_REPORT_URL="https://bugs.centos.org/"

    CENTOS_MANTISBT_PROJECT="CentOS-7"
    CENTOS_MANTISBT_PROJECT_VERSION="7"
    REDHAT_SUPPORT_PRODUCT="centos"
    REDHAT_SUPPORT_PRODUCT_VERSION="7"
"""
)

OS_RELEASE_REDHAT_7 = dedent(
    """\
    NAME="Red Hat Enterprise Linux Server"
    VERSION="7.5 (Maipo)"
    ID="rhel"
    ID_LIKE="fedora"
    VARIANT="Server"
    VARIANT_ID="server"
    VERSION_ID="7.5"
    PRETTY_NAME="Red Hat"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:redhat:enterprise_linux:7.5:GA:server"
    HOME_URL="https://www.redhat.com/"
    BUG_REPORT_URL="https://bugzilla.redhat.com/"

    REDHAT_BUGZILLA_PRODUCT="Red Hat Enterprise Linux 7"
    REDHAT_BUGZILLA_PRODUCT_VERSION=7.5
    REDHAT_SUPPORT_PRODUCT="Red Hat Enterprise Linux"
    REDHAT_SUPPORT_PRODUCT_VERSION="7.5"
"""
)

OS_RELEASE_ALMALINUX_8 = dedent(
    """\
    NAME="AlmaLinux"
    VERSION="8.3 (Purple Manul)"
    ID="almalinux"
    ID_LIKE="rhel centos fedora"
    VERSION_ID="8.3"
    PLATFORM_ID="platform:el8"
    PRETTY_NAME="AlmaLinux 8.3 (Purple Manul)"
    ANSI_COLOR="0;34"
    CPE_NAME="cpe:/o:almalinux:almalinux:8.3:GA"
    HOME_URL="https://almalinux.org/"
    BUG_REPORT_URL="https://bugs.almalinux.org/"

    ALMALINUX_MANTISBT_PROJECT="AlmaLinux-8"
    ALMALINUX_MANTISBT_PROJECT_VERSION="8.3"
"""
)

OS_RELEASE_EUROLINUX_7 = dedent(
    """\
    VERSION="7.9 (Minsk)"
    ID="eurolinux"
    ID_LIKE="rhel scientific centos fedora"
    VERSION_ID="7.9"
    PRETTY_NAME="EuroLinux 7.9 (Minsk)"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:eurolinux:eurolinux:7.9:GA"
    HOME_URL="http://www.euro-linux.com/"
    BUG_REPORT_URL="mailto:support@euro-linux.com"
    REDHAT_BUGZILLA_PRODUCT="EuroLinux 7"
    REDHAT_BUGZILLA_PRODUCT_VERSION=7.9
    REDHAT_SUPPORT_PRODUCT="EuroLinux"
    REDHAT_SUPPORT_PRODUCT_VERSION="7.9"
"""
)

OS_RELEASE_EUROLINUX_8 = dedent(
    """\
    NAME="EuroLinux"
    VERSION="8.4 (Vaduz)"
    ID="eurolinux"
    ID_LIKE="rhel fedora centos"
    VERSION_ID="8.4"
    PLATFORM_ID="platform:el8"
    PRETTY_NAME="EuroLinux 8.4 (Vaduz)"
    ANSI_COLOR="0;34"
    CPE_NAME="cpe:/o:eurolinux:eurolinux:8"
    HOME_URL="https://www.euro-linux.com/"
    BUG_REPORT_URL="https://github.com/EuroLinux/eurolinux-distro-bugs-and-rfc/"
    REDHAT_SUPPORT_PRODUCT="EuroLinux"
    REDHAT_SUPPORT_PRODUCT_VERSION="8"
"""
)

OS_RELEASE_MIRACLELINUX_8 = dedent(
    """\
    NAME="MIRACLE LINUX"
    VERSION="8.4 (Peony)"
    ID="miraclelinux"
    ID_LIKE="rhel fedora"
    PLATFORM_ID="platform:el8"
    VERSION_ID="8"
    PRETTY_NAME="MIRACLE LINUX 8.4 (Peony)"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:cybertrust_japan:miracle_linux:8"
    HOME_URL="https://www.cybertrust.co.jp/miracle-linux/"
    DOCUMENTATION_URL="https://www.miraclelinux.com/support/miraclelinux8"
    BUG_REPORT_URL="https://bugzilla.asianux.com/"
    MIRACLELINUX_SUPPORT_PRODUCT="MIRACLE LINUX"
    MIRACLELINUX_SUPPORT_PRODUCT_VERSION="8"
"""
)

OS_RELEASE_ROCKY_8 = dedent(
    """\
    NAME="Rocky Linux"
    VERSION="8.3 (Green Obsidian)"
    ID="rocky"
    ID_LIKE="rhel fedora"
    VERSION_ID="8.3"
    PLATFORM_ID="platform:el8"
    PRETTY_NAME="Rocky Linux 8.3 (Green Obsidian)"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:rocky:rocky:8"
    HOME_URL="https://rockylinux.org/"
    BUG_REPORT_URL="https://bugs.rockylinux.org/"
    ROCKY_SUPPORT_PRODUCT="Rocky Linux"
    ROCKY_SUPPORT_PRODUCT_VERSION="8"
"""
)

OS_RELEASE_VIRTUOZZO_8 = dedent(
    """\
    NAME="Virtuozzo Linux"
    VERSION="8"
    ID="virtuozzo"
    ID_LIKE="rhel fedora"
    VERSION_ID="8"
    PLATFORM_ID="platform:el8"
    PRETTY_NAME="Virtuozzo Linux"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:virtuozzoproject:vzlinux:8"
    HOME_URL="https://www.vzlinux.org"
    BUG_REPORT_URL="https://bugs.openvz.org"
"""
)

OS_RELEASE_CLOUDLINUX_8 = dedent(
    """\
    NAME="CloudLinux"
    VERSION="8.4 (Valery Rozhdestvensky)"
    ID="cloudlinux"
    ID_LIKE="rhel fedora centos"
    VERSION_ID="8.4"
    PLATFORM_ID="platform:el8"
    PRETTY_NAME="CloudLinux 8.4 (Valery Rozhdestvensky)"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:cloudlinux:cloudlinux:8.4:GA:server"
    HOME_URL="https://www.cloudlinux.com/"
    BUG_REPORT_URL="https://www.cloudlinux.com/support"
"""
)

OS_RELEASE_OPENEULER_20 = dedent(
    """\
    NAME="openEuler"
    VERSION="20.03 (LTS-SP2)"
    ID="openEuler"
    VERSION_ID="20.03"
    PRETTY_NAME="openEuler 20.03 (LTS-SP2)"
    ANSI_COLOR="0;31"
"""
)

OS_RELEASE_OPENCLOUDOS_8 = dedent(
    """\
    NAME="OpenCloudOS"
    VERSION="8.6"
    ID="OpenCloudOS"
    ID_LIKE="rhel fedora"
    VERSION_ID="8.6"
    PLATFORM_ID="platform:oc8"
    PRETTY_NAME="OpenCloudOS 8.6"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:opencloudos:opencloudos:8"
    HOME_URL="https://www.opencloudos.org/"
    BUG_REPORT_URL="https://bugs.opencloudos.tech/"
"""
)

OS_RELEASE_TENCENTOS_3 = dedent(
    """\
    NAME="TencentOS"
    VERSION="3.1"
    ID="TencentOS"
    ID_LIKE="rhel fedora centos"
    VERSION_ID="3.1"
    PLATFORM_ID="platform:el3"
    PRETTY_NAME="TencentOS 3.1"
    ANSI_COLOR="0;31"
    CPE_NAME="cpe:/o:tencentos:tencentos:3"
"""
)

REDHAT_RELEASE_CENTOS_6 = "CentOS release 6.10 (Final)"
REDHAT_RELEASE_CENTOS_7 = "CentOS Linux release 7.5.1804 (Core)"
REDHAT_RELEASE_REDHAT_6 = (
    "Red Hat Enterprise Linux Server release 6.10 (Santiago)"
)
REDHAT_RELEASE_REDHAT_7 = "Red Hat Enterprise Linux Server release 7.5 (Maipo)"
REDHAT_RELEASE_ALMALINUX_8 = "AlmaLinux release 8.3 (Purple Manul)"
REDHAT_RELEASE_EUROLINUX_7 = "EuroLinux release 7.9 (Minsk)"
REDHAT_RELEASE_EUROLINUX_8 = "EuroLinux release 8.4 (Vaduz)"
REDHAT_RELEASE_MIRACLELINUX_8 = "MIRACLE LINUX release 8.4 (Peony)"
REDHAT_RELEASE_ROCKY_8 = "Rocky Linux release 8.3 (Green Obsidian)"
REDHAT_RELEASE_VIRTUOZZO_8 = "Virtuozzo Linux release 8"
REDHAT_RELEASE_CLOUDLINUX_8 = "CloudLinux release 8.4 (Valery Rozhdestvensky)"
OS_RELEASE_DEBIAN = dedent(
    """\
    PRETTY_NAME="Debian GNU/Linux 9 (stretch)"
    NAME="Debian GNU/Linux"
    VERSION_ID="9"
    VERSION="9 (stretch)"
    ID=debian
    HOME_URL="https://www.debian.org/"
    SUPPORT_URL="https://www.debian.org/support"
    BUG_REPORT_URL="https://bugs.debian.org/"
"""
)

OS_RELEASE_UBUNTU = dedent(
    """\
    NAME="Ubuntu"\n
    # comment test
    VERSION="16.04.3 LTS (Xenial Xerus)"\n
    ID=ubuntu\n
    ID_LIKE=debian\n
    PRETTY_NAME="Ubuntu 16.04.3 LTS"\n
    VERSION_ID="16.04"\n
    HOME_URL="http://www.ubuntu.com/"\n
    SUPPORT_URL="http://help.ubuntu.com/"\n
    BUG_REPORT_URL="http://bugs.launchpad.net/ubuntu/"\n
    VERSION_CODENAME=xenial\n
    UBUNTU_CODENAME=xenial\n
"""
)

OS_RELEASE_PHOTON = """\
        NAME="VMware Photon OS"
        VERSION="4.0"
        ID=photon
        VERSION_ID=4.0
        PRETTY_NAME="VMware Photon OS/Linux"
        ANSI_COLOR="1;34"
        HOME_URL="https://vmware.github.io/photon/"
        BUG_REPORT_URL="https://github.com/vmware/photon/issues"
"""

OS_RELEASE_OPENMANDRIVA = dedent(
    """\
    NAME="OpenMandriva Lx"\n
    VERSION="4.90 (Nickel) Cooker"\n
    ID="openmandriva"\n
    VERSION_ID="4.90"\n
    PRETTY_NAME="OpenMandriva Lx 4.90 (Nickel) Cooker"\n
    BUILD_ID="20220606.19"\n
    VERSION_CODENAME="nickel"\n
    ANSI_COLOR="1;43"\n
    LOGO="openmandriva"\n
    CPE_NAME="cpe:/o:openmandriva:openmandriva_lx:4.90"\n
    HOME_URL="http://openmandriva.org/"\n
    BUG_REPORT_URL="http://issues.openmandriva.org/"\n
    SUPPORT_URL="https://forum.openmandriva.org"\n
    PRIVACY_POLICY_URL="https://www.openmandriva.org/tos"\n
"""
)

OS_RELEASE_COS = dedent(
    """\
    NAME="Container-Optimized OS"
    ID=cos
    PRETTY_NAME="Container-Optimized OS from Google"
    HOME_URL="https://cloud.google.com/container-optimized-os/docs"
    BUG_REPORT_URL="https://cloud.google.com/container-optimized-os/docs/resources/support-policy#contact_us"
    VERSION=93
    VERSION_ID=93
"""
)

OS_RELEASE_MARINER = dedent(
    """\
    NAME="CBL-Mariner"
    VERSION="2.0.20221004"
    ID=mariner
    VERSION_ID=2.0
    PRETTY_NAME="CBL-Mariner/Linux"
    ANSI_COLOR="1;34"
    HOME_URL="https://aka.ms/cbl-mariner"
    BUG_REPORT_URL="https://aka.ms/cbl-mariner"
    SUPPORT_URL="https://aka.ms/cbl-mariner"
"""
)

OS_RELEASE_AZURELINUX = dedent(
    """\
    NAME="Microsoft Azure Linux"
    VERSION="3.0.20240206"
    ID=azurelinux
    VERSION_ID="3.0"
    PRETTY_NAME="Microsoft Azure Linux 3.0"
    ANSI_COLOR="1;34"
    HOME_URL="https://aka.ms/azurelinux"
    BUG_REPORT_URL="https://aka.ms/azurelinux"
    SUPPORT_URL="https://aka.ms/azurelinux"
"""
)


@pytest.mark.usefixtures("fake_filesystem")
class TestUtil:
    def test_parse_mount_info_no_opts_no_arg(self):
        result = util.parse_mount_info("/home", MOUNT_INFO, LOG)
        assert ("/dev/sda2", "xfs", "/home") == result

    def test_parse_mount_info_no_opts_arg(self):
        result = util.parse_mount_info("/home", MOUNT_INFO, LOG, False)
        assert ("/dev/sda2", "xfs", "/home") == result

    def test_parse_mount_info_with_opts(self):
        result = util.parse_mount_info("/", MOUNT_INFO, LOG, True)
        assert ("/dev/sda1", "btrfs", "/", "ro,relatime") == result

    @pytest.mark.parametrize(
        "opt, expected_result",
        [
            ("rw", True),
            ("relatime", True),
            ("idmapped", True),
            ("noexec", False),
        ],
    )
    @mock.patch(
        M_PATH + "get_mount_info",
        return_value=("/dev/sda", "ext4", "/", "rw,relatime,idmapped"),
    )
    def test_has_mount_opt(self, m_get_mount_info, opt, expected_result):
        assert expected_result == util.has_mount_opt("/", opt)

    @mock.patch(M_PATH + "get_mount_info")
    def test_mount_is_rw(self, m_mount_info):
        m_mount_info.return_value = ("/dev/sda1", "btrfs", "/", "rw,relatime")
        is_rw = util.mount_is_read_write("/")
        assert is_rw is True

    @mock.patch(M_PATH + "get_mount_info")
    def test_mount_is_ro(self, m_mount_info):
        m_mount_info.return_value = ("/dev/sda1", "btrfs", "/", "ro,relatime")
        is_rw = util.mount_is_read_write("/")
        assert is_rw is False

    def test_read_conf(self, mocker):
        mocker.patch(
            "cloudinit.util.load_text_file", return_value='{"a": "b"}'
        )
        assert util.read_conf("any") == {"a": "b"}

    @skipUnlessJinja()
    def test_read_conf_with_template(self, mocker, caplog):
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch(
            "cloudinit.util.load_text_file",
            return_value='## template: jinja\n{"a": "{{c}}"}',
        )
        mocker.patch(
            "cloudinit.handlers.jinja_template.load_text_file",
            return_value='{"c": "d"}',
        )

        conf = util.read_conf("cfg_path", instance_data_file="vars_path")
        assert conf == {"a": "d"}
        assert (
            "Applied instance data in 'vars_path' to configuration loaded "
            "from 'cfg_path'"
        ) in caplog.text

    @skipUnlessJinja()
    def test_read_conf_with_failed_config_json(self, mocker, caplog):
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch(
            "cloudinit.util.load_text_file",
            return_value='## template: jinja\n{"a": "{{c}}"',  # missing }
        )
        mocker.patch(
            "cloudinit.handlers.jinja_template.load_text_file",
            return_value='{"c": "d"}',
        )
        conf = util.read_conf("cfg_path", instance_data_file="vars_path")
        assert "Failed loading yaml blob" in caplog.text
        assert conf == {}

    @skipUnlessJinja()
    def test_read_conf_with_failed_instance_data_json(self, mocker, caplog):
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch(
            "cloudinit.util.load_text_file",
            return_value='## template: jinja\n{"a": "{{c}}"}',
        )
        mocker.patch(
            "cloudinit.handlers.jinja_template.load_text_file",
            return_value='{"c": "d"',  # missing }
        )
        conf = util.read_conf("cfg_path", instance_data_file="vars_path")
        assert "Could not apply Jinja template" in caplog.text
        assert conf == {"a": "{{c}}"}

    @pytest.mark.parametrize(
        "template",
        [
            '{"a": "{{c} } }"',
            '{"a": "{{c} } "',
            "{% if c %} C is present {% else % } C is NOT present {% endif %}",
        ],
    )
    @skipUnlessJinja()
    def test_read_conf_with_config_invalid_jinja_syntax(
        self, mocker, caplog, template
    ):
        mocker.patch("os.path.exists", return_value=True)
        mocker.patch(
            "cloudinit.util.load_text_file",
            return_value="## template: jinja\n" + template,
        )
        mocker.patch(
            "cloudinit.handlers.jinja_template.load_text_file",
            return_value='{"c": "d"}',
        )
        conf = util.read_conf("cfg_path", instance_data_file="vars_path")
        assert (
            "Failed to render templated yaml config file 'cfg_path'"
            in caplog.text
        )
        assert conf == {}

    @mock.patch(
        M_PATH + "read_conf",
        side_effect=(OSError(errno.EACCES, "Not allowed"), {"0": "0"}),
    )
    def test_read_conf_d_no_permissions(
        self, m_read_conf, caplog, capsys, tmpdir
    ):
        """If a user has not read permission to read a config file then
        there is no exception nor stderr output and the user is informed via
        logging warnings.

        Note: This is used in cmd, therefore want to keep the invariant of
        not outputing to the console and log file permission errors.
        """
        confs = []
        for i in range(2):
            confs.append(tmpdir.join(f"conf-{i}.cfg"))
            confs[i].write("{}")
        assert {"0": "0"} == util.read_conf_d(tmpdir)
        assert (
            caplog.text.count(f"REDACTED config part {tmpdir}/conf-1.cfg") == 1
        )
        assert m_read_conf.call_count == 2
        out, err = capsys.readouterr()
        assert not out
        assert not err

    @pytest.mark.parametrize(
        "create_confd,expected_call",
        [
            (False, mock.call(deque())),
            (True, mock.call(deque([{"my_config": "foo"}]))),
        ],
    )
    @mock.patch(M_PATH + "mergemanydict")
    @mock.patch(M_PATH + "read_conf_d", return_value={"my_config": "foo"})
    @mock.patch(
        M_PATH + "read_conf", side_effect=OSError(errno.EACCES, "Not allowed")
    )
    def test_read_conf_with_confd_no_permissions(
        self,
        m_read_conf,
        m_read_confd,
        m_mergemanydict,
        create_confd,
        expected_call,
        caplog,
        capsys,
        tmpdir,
    ):
        """Read a conf file without permission.

        sys output is empty and the user is informed via logging warnings.

        Note: This is used in cmd, therefore want to keep the invariant of
        not outputing to the console and log file permission errors.
        """
        conf_fn = tmpdir.join("conf.cfg")
        if create_confd:
            confd_fn = tmpdir.mkdir("conf.cfg.d")
        util.read_conf_with_confd(conf_fn)
        assert caplog.text.count(f"REDACTED config part {conf_fn}") == 1
        assert m_read_conf.call_count == 1
        out, err = capsys.readouterr()
        assert not out
        assert not err
        if create_confd:
            assert [
                mock.call(confd_fn, instance_data_file=None)
            ] == m_read_confd.call_args_list
        assert [expected_call] == m_mergemanydict.call_args_list

    @pytest.mark.parametrize("custom_cloud_dir", [True, False])
    @mock.patch(M_PATH + "os.path.isfile", return_value=True)
    @mock.patch(M_PATH + "os.path.isdir", return_value=True)
    def test_fetch_ssl_details(
        self, m_isdir, m_isfile, custom_cloud_dir, tmpdir
    ):
        cloud_dir = "/var/lib/cloud"
        if custom_cloud_dir:
            cloud_dir = tmpdir.join("cloud")
        cert = os.path.join(cloud_dir, "instance", "data", "ssl", "cert.pem")
        key = os.path.join(cloud_dir, "instance", "data", "ssl", "key.pem")

        paths = Paths({"cloud_dir": cloud_dir})
        ssl_details = util.fetch_ssl_details(paths)
        assert {"cert_file": cert, "key_file": key} == ssl_details
        assert 2 == m_isdir.call_count == m_isfile.call_count


class TestSymlink(CiTestCase):
    def test_sym_link_simple(self):
        tmpd = self.tmp_dir()
        link = self.tmp_path("link", tmpd)
        target = self.tmp_path("target", tmpd)
        util.write_file(target, "hello")

        util.sym_link(target, link)
        self.assertTrue(os.path.exists(link))
        self.assertTrue(os.path.islink(link))

    def test_sym_link_source_exists(self):
        tmpd = self.tmp_dir()
        link = self.tmp_path("link", tmpd)
        target = self.tmp_path("target", tmpd)
        target2 = self.tmp_path("target2", tmpd)
        util.write_file(target, "hello")
        util.write_file(target2, "hello2")

        util.sym_link(target, link)
        self.assertTrue(os.path.exists(link))

        util.sym_link(target2, link, force=True)
        self.assertTrue(os.path.exists(link))
        self.assertEqual("hello2", util.load_text_file(link))

    def test_sym_link_dangling_link(self):
        tmpd = self.tmp_dir()
        link = self.tmp_path("link", tmpd)
        target = self.tmp_path("target", tmpd)

        util.sym_link(target, link)
        self.assertTrue(os.path.islink(link))
        self.assertFalse(os.path.exists(link))

        util.sym_link(target, link, force=True)
        self.assertTrue(os.path.islink(link))
        self.assertFalse(os.path.exists(link))

    def test_sym_link_create_dangling(self):
        tmpd = self.tmp_dir()
        link = self.tmp_path("link", tmpd)
        target = self.tmp_path("target", tmpd)

        util.sym_link(target, link)
        self.assertTrue(os.path.islink(link))
        self.assertFalse(os.path.exists(link))


class TestUptime(CiTestCase):
    @mock.patch(M_PATH + "boottime")
    @mock.patch(M_PATH + "os.path.exists")
    @mock.patch(M_PATH + "time.time")
    def test_uptime_non_linux_path(self, m_time, m_exists, m_boottime):
        boottime = 1000.0
        uptime = 10.0
        m_boottime.return_value = boottime
        m_time.return_value = boottime + uptime
        m_exists.return_value = False
        result = util.uptime()
        self.assertEqual(str(uptime), result)


class TestShellify(CiTestCase):
    def test_input_dict_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError,
            "Input.*was.*dict.*xpected",
            util.shellify,
            {"mykey": "myval"},
        )

    def test_input_str_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, "Input.*was.*str.*xpected", util.shellify, "foobar"
        )

    def test_value_with_int_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, "shellify.*int", util.shellify, ["foo", 1]
        )

    def test_supports_strings_and_lists(self):
        self.assertEqual(
            "\n".join(
                [
                    "#!/bin/sh",
                    "echo hi mom",
                    "'echo' 'hi dad'",
                    "'echo' 'hi' 'sis'",
                    "",
                ]
            ),
            util.shellify(
                ["echo hi mom", ["echo", "hi dad"], ("echo", "hi", "sis")]
            ),
        )

    def test_supports_comments(self):
        self.assertEqual(
            "\n".join(["#!/bin/sh", "echo start", "echo end", ""]),
            util.shellify(["echo start", None, "echo end"]),
        )


class TestGetHostnameFqdn(CiTestCase):
    def test_get_hostname_fqdn_from_only_cfg_fqdn(self):
        """When cfg only has the fqdn key, derive hostname and fqdn from it."""
        hostname, fqdn, _ = util.get_hostname_fqdn(
            cfg={"fqdn": "myhost.domain.com"}, cloud=None
        )
        self.assertEqual("myhost", hostname)
        self.assertEqual("myhost.domain.com", fqdn)

    def test_get_hostname_fqdn_from_cfg_fqdn_and_hostname(self):
        """When cfg has both fqdn and hostname keys, return them."""
        hostname, fqdn, _ = util.get_hostname_fqdn(
            cfg={"fqdn": "myhost.domain.com", "hostname": "other"}, cloud=None
        )
        self.assertEqual("other", hostname)
        self.assertEqual("myhost.domain.com", fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_with_domain(self):
        """When cfg has only hostname key which represents a fqdn, use that."""
        hostname, fqdn, _ = util.get_hostname_fqdn(
            cfg={"hostname": "myhost.domain.com"}, cloud=None
        )
        self.assertEqual("myhost", hostname)
        self.assertEqual("myhost.domain.com", fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_without_domain(self):
        """When cfg has a hostname without a '.' query cloud.get_hostname."""
        cloud = mock.MagicMock()
        cloud.get_hostname.return_value = DataSourceHostname(
            "cloudhost.mycloud.com", False
        )
        hostname, fqdn, _ = util.get_hostname_fqdn(
            cfg={"hostname": "myhost"}, cloud=cloud
        )
        self.assertEqual("myhost", hostname)
        self.assertEqual("cloudhost.mycloud.com", fqdn)
        assert [
            mock.call(fqdn=True, metadata_only=False)
        ] == cloud.get_hostname.call_args_list

    def test_get_hostname_fqdn_from_without_fqdn_or_hostname(self):
        """When cfg has neither hostname nor fqdn cloud.get_hostname."""
        cloud = mock.MagicMock()
        cloud.get_hostname.side_effect = (
            DataSourceHostname("cloudhost.mycloud.com", False),
            DataSourceHostname("cloudhost", False),
        )
        hostname, fqdn, _ = util.get_hostname_fqdn(cfg={}, cloud=cloud)
        self.assertEqual("cloudhost", hostname)
        self.assertEqual("cloudhost.mycloud.com", fqdn)
        assert [
            mock.call(fqdn=True, metadata_only=False),
            mock.call(metadata_only=False),
        ] == cloud.get_hostname.call_args_list

    def test_get_hostname_fqdn_from_passes_metadata_only_to_cloud(self):
        """Calls to cloud.get_hostname pass the metadata_only parameter."""
        cloud = mock.MagicMock()
        cloud.get_hostname.side_effect = (
            DataSourceHostname("cloudhost.mycloud.com", False),
            DataSourceHostname("cloudhost", False),
        )
        _hn, _fqdn, _def_hostname = util.get_hostname_fqdn(
            cfg={}, cloud=cloud, metadata_only=True
        )
        assert [
            mock.call(fqdn=True, metadata_only=True),
            mock.call(metadata_only=True),
        ] == cloud.get_hostname.call_args_list


class TestBlkid(CiTestCase):
    ids = {
        "id01": "1111-1111",
        "id02": "22222222-2222",
        "id03": "33333333-3333",
        "id04": "44444444-4444",
        "id05": "55555555-5555-5555-5555-555555555555",
        "id06": "66666666-6666-6666-6666-666666666666",
        "id07": "52894610484658920398",
        "id08": "86753098675309867530",
        "id09": "99999999-9999-9999-9999-999999999999",
    }

    blkid_out = dedent(
        """\
        /dev/loop0: TYPE="squashfs"
        /dev/loop1: TYPE="squashfs"
        /dev/loop2: TYPE="squashfs"
        /dev/loop3: TYPE="squashfs"
        /dev/sda1: UUID="{id01}" TYPE="vfat" PARTUUID="{id02}"
        /dev/sda2: UUID="{id03}" TYPE="ext4" PARTUUID="{id04}"
        /dev/sda3: UUID="{id05}" TYPE="ext4" PARTUUID="{id06}"
        /dev/sda4: LABEL="default" UUID="{id07}" UUID_SUB="{id08}" """
        """TYPE="zfs_member" PARTUUID="{id09}"
        /dev/loop4: TYPE="squashfs"
      """
    )

    maxDiff = None

    def _get_expected(self):
        return {
            "/dev/loop0": {"DEVNAME": "/dev/loop0", "TYPE": "squashfs"},
            "/dev/loop1": {"DEVNAME": "/dev/loop1", "TYPE": "squashfs"},
            "/dev/loop2": {"DEVNAME": "/dev/loop2", "TYPE": "squashfs"},
            "/dev/loop3": {"DEVNAME": "/dev/loop3", "TYPE": "squashfs"},
            "/dev/loop4": {"DEVNAME": "/dev/loop4", "TYPE": "squashfs"},
            "/dev/sda1": {
                "DEVNAME": "/dev/sda1",
                "TYPE": "vfat",
                "UUID": self.ids["id01"],
                "PARTUUID": self.ids["id02"],
            },
            "/dev/sda2": {
                "DEVNAME": "/dev/sda2",
                "TYPE": "ext4",
                "UUID": self.ids["id03"],
                "PARTUUID": self.ids["id04"],
            },
            "/dev/sda3": {
                "DEVNAME": "/dev/sda3",
                "TYPE": "ext4",
                "UUID": self.ids["id05"],
                "PARTUUID": self.ids["id06"],
            },
            "/dev/sda4": {
                "DEVNAME": "/dev/sda4",
                "TYPE": "zfs_member",
                "LABEL": "default",
                "UUID": self.ids["id07"],
                "UUID_SUB": self.ids["id08"],
                "PARTUUID": self.ids["id09"],
            },
        }

    @mock.patch("cloudinit.subp.subp")
    def test_functional_blkid(self, m_subp):
        m_subp.return_value = SubpResult(self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(), util.blkid())
        m_subp.assert_called_with(
            ["blkid", "-o", "full"], capture=True, decode="replace"
        )

    @mock.patch("cloudinit.subp.subp")
    def test_blkid_no_cache_uses_no_cache(self, m_subp):
        """blkid should turn off cache if disable_cache is true."""
        m_subp.return_value = SubpResult(self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(), util.blkid(disable_cache=True))
        m_subp.assert_called_with(
            ["blkid", "-o", "full", "-c", "/dev/null"],
            capture=True,
            decode="replace",
        )


@mock.patch("cloudinit.util.subp.which")
@mock.patch("cloudinit.util.subp.subp")
class TestUdevadmSettle(CiTestCase):
    def test_with_no_params(self, m_subp, m_which):
        """called with no parameters."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        util.udevadm_settle()
        m_subp.assert_called_once_with(["udevadm", "settle"])

    def test_udevadm_not_present(self, m_subp, m_which):
        """where udevadm program does not exist should not invoke subp."""
        m_which.side_effect = lambda m: m in ("",)
        util.udevadm_settle()
        m_which.assert_called_once_with("udevadm")
        m_subp.assert_not_called()

    def test_with_exists_and_not_exists(self, m_subp, m_which):
        """with exists=file where file does not exist should invoke subp."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        mydev = self.tmp_path("mydev")
        util.udevadm_settle(exists=mydev)
        m_subp.assert_called_once_with(
            ["udevadm", "settle", "--exit-if-exists=%s" % mydev]
        )

    def test_with_exists_and_file_exists(self, m_subp, m_which):
        """with exists=file where file does exist should only invoke subp
        once for 'which' call."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        mydev = self.tmp_path("mydev")
        util.write_file(mydev, "foo\n")
        util.udevadm_settle(exists=mydev)
        m_which.assert_called_once_with("udevadm")
        m_subp.assert_not_called()

    def test_with_timeout_int(self, m_subp, m_which):
        """timeout can be an integer."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        timeout = 9
        util.udevadm_settle(timeout=timeout)
        m_subp.assert_called_once_with(
            ["udevadm", "settle", "--timeout=%s" % timeout]
        )

    def test_with_timeout_string(self, m_subp, m_which):
        """timeout can be a string."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        timeout = "555"
        util.udevadm_settle(timeout=timeout)
        m_subp.assert_called_once_with(
            ["udevadm", "settle", "--timeout=%s" % timeout]
        )

    def test_with_exists_and_timeout(self, m_subp, m_which):
        """test call with both exists and timeout."""
        m_which.side_effect = lambda m: m in ("udevadm",)
        mydev = self.tmp_path("mydev")
        timeout = "3"
        util.udevadm_settle(exists=mydev, timeout=timeout)
        m_subp.assert_called_once_with(
            [
                "udevadm",
                "settle",
                "--exit-if-exists=%s" % mydev,
                "--timeout=%s" % timeout,
            ]
        )

    def test_subp_exception_raises_to_caller(self, m_subp, m_which):
        m_which.side_effect = lambda m: m in ("udevadm",)
        m_subp.side_effect = subp.ProcessExecutionError("BOOM")
        self.assertRaises(subp.ProcessExecutionError, util.udevadm_settle)


@mock.patch("os.path.exists")
class TestGetLinuxDistro(CiTestCase):
    def setUp(self):
        util.get_linux_distro.cache_clear()

    @classmethod
    def os_release_exists(self, path):
        """Side effect function"""
        if path == "/etc/os-release":
            return 1

    @classmethod
    def redhat_release_exists(self, path):
        """Side effect function"""
        if path == "/etc/redhat-release":
            return 1

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_distro_quoted_name(self, m_os_release, m_path_exists):
        """Verify we get the correct name if the os-release file has
        the distro name in quotes"""
        m_os_release.return_value = OS_RELEASE_SLES
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("sles", "12.3", platform.machine()), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_distro_bare_name(self, m_os_release, m_path_exists):
        """Verify we get the correct name if the os-release file does not
        have the distro name in quotes"""
        m_os_release.return_value = OS_RELEASE_UBUNTU
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("ubuntu", "16.04", "xenial"), dist)

    @mock.patch("platform.system")
    @mock.patch("platform.release")
    @mock.patch(M_PATH + "_parse_redhat_release")
    def test_get_linux_freebsd(
        self,
        m_parse_redhat_release,
        m_platform_release,
        m_platform_system,
        m_path_exists,
    ):
        """Verify we get the correct name and release name on FreeBSD."""
        m_path_exists.return_value = False
        m_platform_release.return_value = "12.0-RELEASE-p10"
        m_platform_system.return_value = "FreeBSD"
        m_parse_redhat_release.return_value = {}
        util.is_BSD.cache_clear()
        dist = util.get_linux_distro()
        self.assertEqual(("freebsd", "12.0-RELEASE-p10", ""), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_centos6(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on CentOS 6."""
        m_os_release.return_value = REDHAT_RELEASE_CENTOS_6
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("centos", "6.10", "Final"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_centos7_redhat_release(self, m_os_release, m_exists):
        """Verify the correct release info on CentOS 7 without os-release."""
        m_os_release.return_value = REDHAT_RELEASE_CENTOS_7
        m_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("centos", "7.5.1804", "Core"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_redhat7_osrelease(self, m_os_release, m_path_exists):
        """Verify redhat 7 read from os-release."""
        m_os_release.return_value = OS_RELEASE_REDHAT_7
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("redhat", "7.5", "Maipo"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_redhat7_rhrelease(self, m_os_release, m_path_exists):
        """Verify redhat 7 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_REDHAT_7
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("redhat", "7.5", "Maipo"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_redhat6_rhrelease(self, m_os_release, m_path_exists):
        """Verify redhat 6 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_REDHAT_6
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("redhat", "6.10", "Santiago"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_copr_centos(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on COPR CentOS."""
        m_os_release.return_value = OS_RELEASE_CENTOS
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("centos", "7", "Core"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_almalinux8_rhrelease(self, m_os_release, m_path_exists):
        """Verify almalinux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_ALMALINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("almalinux", "8.3", "Purple Manul"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_almalinux8_osrelease(self, m_os_release, m_path_exists):
        """Verify almalinux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_ALMALINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("almalinux", "8.3", "Purple Manul"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_eurolinux7_rhrelease(self, m_os_release, m_path_exists):
        """Verify eurolinux 7 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_EUROLINUX_7
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("eurolinux", "7.9", "Minsk"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_eurolinux7_osrelease(self, m_os_release, m_path_exists):
        """Verify eurolinux 7 read from os-release."""
        m_os_release.return_value = OS_RELEASE_EUROLINUX_7
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("eurolinux", "7.9", "Minsk"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_eurolinux8_rhrelease(self, m_os_release, m_path_exists):
        """Verify eurolinux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_EUROLINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("eurolinux", "8.4", "Vaduz"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_eurolinux8_osrelease(self, m_os_release, m_path_exists):
        """Verify eurolinux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_EUROLINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("eurolinux", "8.4", "Vaduz"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_miraclelinux8_rhrelease(
        self, m_os_release, m_path_exists
    ):
        """Verify miraclelinux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_MIRACLELINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("miracle", "8.4", "Peony"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_miraclelinux8_osrelease(
        self, m_os_release, m_path_exists
    ):
        """Verify miraclelinux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_MIRACLELINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("miraclelinux", "8", "Peony"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_rocky8_rhrelease(self, m_os_release, m_path_exists):
        """Verify rocky linux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_ROCKY_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("rocky", "8.3", "Green Obsidian"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_rocky8_osrelease(self, m_os_release, m_path_exists):
        """Verify rocky linux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_ROCKY_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("rocky", "8.3", "Green Obsidian"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_virtuozzo8_rhrelease(self, m_os_release, m_path_exists):
        """Verify virtuozzo linux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_VIRTUOZZO_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("virtuozzo", "8", "Virtuozzo Linux"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_virtuozzo8_osrelease(self, m_os_release, m_path_exists):
        """Verify virtuozzo linux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_VIRTUOZZO_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("virtuozzo", "8", "Virtuozzo Linux"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_cloud8_rhrelease(self, m_os_release, m_path_exists):
        """Verify cloudlinux 8 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_CLOUDLINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("cloudlinux", "8.4", "Valery Rozhdestvensky"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_cloud8_osrelease(self, m_os_release, m_path_exists):
        """Verify cloudlinux 8 read from os-release."""
        m_os_release.return_value = OS_RELEASE_CLOUDLINUX_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("cloudlinux", "8.4", "Valery Rozhdestvensky"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_debian(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on Debian."""
        m_os_release.return_value = OS_RELEASE_DEBIAN
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("debian", "9", "stretch"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_openeuler(self, m_os_release, m_path_exists):
        """Verify get the correct name and release name on Openeuler."""
        m_os_release.return_value = OS_RELEASE_OPENEULER_20
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("openEuler", "20.03", "LTS-SP2"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_opencloudos(self, m_os_release, m_path_exists):
        """Verify get the correct name and release name on OpenCloudOS."""
        m_os_release.return_value = OS_RELEASE_OPENCLOUDOS_8
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("OpenCloudOS", "8.6", ""), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_tencentos(self, m_os_release, m_path_exists):
        """Verify get the correct name and release name on TencentOS."""
        m_os_release.return_value = OS_RELEASE_TENCENTOS_3
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("TencentOS", "3.1", ""), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_opensuse(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
        prior to openSUSE Leap 15.
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("opensuse", "42.3", platform.machine()), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_opensuse_l15(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
        for openSUSE Leap 15.0 and later.
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE_L15
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("opensuse-leap", "15.0", platform.machine()), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_opensuse_tw(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
        for openSUSE Tumbleweed
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE_TW
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(
            ("opensuse-tumbleweed", "20180920", platform.machine()), dist
        )

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_photon_os_release(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on PhotonOS"""
        m_os_release.return_value = OS_RELEASE_PHOTON
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("photon", "4.0", "VMware Photon OS/Linux"), dist)

    @mock.patch("cloudinit.util.load_text_file")
    def test_get_linux_mariner_os_release(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on MarinerOS"""
        m_os_release.return_value = OS_RELEASE_MARINER
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("mariner", "2.0", ""), dist)

    @mock.patch("cloudinit.util.load_text_file")
    def test_get_linux_azurelinux_os_release(
        self, m_os_release, m_path_exists
    ):
        """Verify we get the correct name and machine arch on Azure Linux"""
        m_os_release.return_value = OS_RELEASE_AZURELINUX
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("azurelinux", "3.0", ""), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_openmandriva(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on OpenMandriva"""
        m_os_release.return_value = OS_RELEASE_OPENMANDRIVA
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("openmandriva", "4.90", "nickel"), dist)

    @mock.patch(M_PATH + "load_text_file")
    def test_get_linux_cos(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on COS"""
        m_os_release.return_value = OS_RELEASE_COS
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(("cos", "93", ""), dist)

    @mock.patch("platform.system")
    @mock.patch("platform.dist", create=True)
    def test_get_linux_distro_no_data(
        self, m_platform_dist, m_platform_system, m_path_exists
    ):
        """Verify we get no information if os-release does not exist"""
        m_platform_dist.return_value = ("", "", "")
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(("", "", ""), dist)

    @mock.patch("platform.system")
    @mock.patch("platform.dist", create=True)
    def test_get_linux_distro_no_impl(
        self, m_platform_dist, m_platform_system, m_path_exists
    ):
        """Verify we get an empty tuple when no information exists and
        Exceptions are not propagated"""
        m_platform_dist.side_effect = Exception()
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(("", "", ""), dist)

    @mock.patch("platform.system")
    @mock.patch("platform.dist", create=True)
    def test_get_linux_distro_plat_data(
        self, m_platform_dist, m_platform_system, m_path_exists
    ):
        """Verify we get the correct platform information"""
        m_platform_dist.return_value = ("foo", "1.1", "aarch64")
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(("foo", "1.1", "aarch64"), dist)


class TestGetVariant:
    @pytest.mark.parametrize(
        "info, expected_variant",
        [
            ({"system": "Linux", "dist": ("almalinux",)}, "almalinux"),
            ({"system": "linux", "dist": ("alpine",)}, "alpine"),
            ({"system": "linux", "dist": ("arch",)}, "arch"),
            ({"system": "linux", "dist": ("azurelinux",)}, "azurelinux"),
            ({"system": "linux", "dist": ("centos",)}, "centos"),
            ({"system": "linux", "dist": ("cloudlinux",)}, "cloudlinux"),
            ({"system": "linux", "dist": ("debian",)}, "debian"),
            ({"system": "linux", "dist": ("eurolinux",)}, "eurolinux"),
            ({"system": "linux", "dist": ("fedora",)}, "fedora"),
            ({"system": "linux", "dist": ("mariner",)}, "mariner"),
            ({"system": "linux", "dist": ("openEuler",)}, "openeuler"),
            ({"system": "linux", "dist": ("OpenCloudOS",)}, "opencloudos"),
            ({"system": "linux", "dist": ("photon",)}, "photon"),
            ({"system": "linux", "dist": ("rhel",)}, "rhel"),
            ({"system": "linux", "dist": ("rocky",)}, "rocky"),
            ({"system": "linux", "dist": ("suse",)}, "suse"),
            ({"system": "linux", "dist": ("TencentOS",)}, "tencentos"),
            ({"system": "linux", "dist": ("virtuozzo",)}, "virtuozzo"),
            ({"system": "linux", "dist": ("ubuntu",)}, "ubuntu"),
            ({"system": "linux", "dist": ("linuxmint",)}, "ubuntu"),
            ({"system": "linux", "dist": ("mint",)}, "ubuntu"),
            ({"system": "linux", "dist": ("redhat",)}, "rhel"),
            ({"system": "linux", "dist": ("opensuse",)}, "suse"),
            ({"system": "linux", "dist": ("opensuse-tumbleweed",)}, "suse"),
            ({"system": "linux", "dist": ("opensuse-leap",)}, "suse"),
            ({"system": "linux", "dist": ("sles",)}, "suse"),
            ({"system": "linux", "dist": ("sle_hpc",)}, "suse"),
            ({"system": "linux", "dist": ("my_distro",)}, "linux"),
            ({"system": "Windows", "dist": ("dontcare",)}, "windows"),
            ({"system": "Darwin", "dist": ("dontcare",)}, "darwin"),
            ({"system": "Freebsd", "dist": ("dontcare",)}, "freebsd"),
            ({"system": "Netbsd", "dist": ("dontcare",)}, "netbsd"),
            ({"system": "Openbsd", "dist": ("dontcare",)}, "openbsd"),
            ({"system": "Dragonfly", "dist": ("dontcare",)}, "dragonfly"),
        ],
    )
    def test_get_variant(self, info, expected_variant):
        """Verify we get the correct variant name"""
        assert util._get_variant(info) == expected_variant


class TestJsonDumps(CiTestCase):
    def test_is_str(self):
        """json_dumps should return a string."""
        self.assertTrue(
            isinstance(atomic_helper.json_dumps({"abc": "123"}), str)
        )

    def test_utf8(self):
        smiley = "\\ud83d\\ude03"
        self.assertEqual(
            {"smiley": smiley},
            json.loads(atomic_helper.json_dumps({"smiley": smiley})),
        )

    def test_non_utf8(self):
        blob = b"\xba\x03Qx-#y\xea"
        self.assertEqual(
            {"blob": "ci-b64:" + base64.b64encode(blob).decode("utf-8")},
            json.loads(atomic_helper.json_dumps({"blob": blob})),
        )


@mock.patch("os.path.exists")
class TestIsLXD(CiTestCase):
    def test_is_lxd_true_on_sock_device(self, m_exists):
        """When lxd's /dev/lxd/sock exists, is_lxd returns true."""
        m_exists.return_value = True
        self.assertTrue(util.is_lxd())
        m_exists.assert_called_once_with("/dev/lxd/sock")

    def test_is_lxd_false_when_sock_device_absent(self, m_exists):
        """When lxd's /dev/lxd/sock is absent, is_lxd returns false."""
        m_exists.return_value = False
        self.assertFalse(util.is_lxd())
        m_exists.assert_called_once_with("/dev/lxd/sock")


class TestReadCcFromCmdline:
    @pytest.mark.parametrize(
        "cmdline,expected_cfg",
        [
            # Return None if cmdline has no cc:<YAML>end_cc content.
            pytest.param(CiTestCase.random_string(), None, id="random_string"),
            # Return None if YAML content is empty string.
            ("foo cc: end_cc bar", None),
            # Return expected dictionary without trailing end_cc marker.
            ("foo cc: ssh_pwauth: true", {"ssh_pwauth": True}),
            # Return expected dictionary w escaped newline and no end_cc.
            ("foo cc: ssh_pwauth: true\\n", {"ssh_pwauth": True}),
            # Return expected dictionary of yaml between cc: and end_cc.
            ("foo cc: ssh_pwauth: true end_cc bar", {"ssh_pwauth": True}),
            # Return dict with list value w escaped newline, no end_cc.
            (
                "cc: ssh_import_id: [smoser, kirkland]\\n",
                {"ssh_import_id": ["smoser", "kirkland"]},
            ),
            # Parse urlencoded brackets in yaml content.
            (
                "cc: ssh_import_id: %5Bsmoser, kirkland%5D end_cc",
                {"ssh_import_id": ["smoser", "kirkland"]},
            ),
            # Parse complete urlencoded yaml content.
            (
                "cc: ssh_import_id%3A%20%5Buser1%2C%20user2%5D end_cc",
                {"ssh_import_id": ["user1", "user2"]},
            ),
            # Parse nested dictionary in yaml content.
            (
                "cc: ntp: {enabled: true, ntp_client: myclient} end_cc",
                {"ntp": {"enabled": True, "ntp_client": "myclient"}},
            ),
            # Parse single mapping value in yaml content.
            ("cc: ssh_import_id: smoser end_cc", {"ssh_import_id": "smoser"}),
            # Parse multiline content with multiple mapping and nested lists.
            (
                "cc: ssh_import_id: [smoser, bob]\\n"
                "runcmd: [ [ ls, -l ], echo hi ] end_cc",
                {
                    "ssh_import_id": ["smoser", "bob"],
                    "runcmd": [["ls", "-l"], "echo hi"],
                },
            ),
            # Parse multiline encoded content w/ mappings and nested lists.
            (
                "cc: ssh_import_id: %5Bsmoser, bob%5D\\n"
                "runcmd: [ [ ls, -l ], echo hi ] end_cc",
                {
                    "ssh_import_id": ["smoser", "bob"],
                    "runcmd": [["ls", "-l"], "echo hi"],
                },
            ),
            # test encoded escaped newlines work.
            #
            # unquote(encoded_content)
            # 'ssh_import_id: [smoser, bob]\\nruncmd: [ [ ls, -l ], echo hi ]'
            (
                (
                    "cc: ssh_import_id%3A%20%5Bsmoser%2C%20bob%5D%5Cn"
                    "runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%2C"
                    "%20echo%20hi%20%5D end_cc"
                ),
                {
                    "ssh_import_id": ["smoser", "bob"],
                    "runcmd": [["ls", "-l"], "echo hi"],
                },
            ),
            # test encoded newlines work.
            #
            # unquote(encoded_content)
            # 'ssh_import_id: [smoser, bob]\nruncmd: [ [ ls, -l ], echo hi ]'
            (
                (
                    "cc: ssh_import_id%3A%20%5Bsmoser%2C%20bob%5D%0A"
                    "runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%2C"
                    "%20echo%20hi%20%5D end_cc"
                ),
                {
                    "ssh_import_id": ["smoser", "bob"],
                    "runcmd": [["ls", "-l"], "echo hi"],
                },
            ),
            # Parse and merge multiple yaml content sections.
            (
                "cc:ssh_import_id: [smoser, bob] end_cc "
                "cc: runcmd: [ [ ls, -l ] ] end_cc",
                {"ssh_import_id": ["smoser", "bob"], "runcmd": [["ls", "-l"]]},
            ),
            # Parse and merge multiple encoded yaml content sections.
            (
                "cc:ssh_import_id%3A%20%5Bsmoser%5D end_cc "
                "cc:runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%20%5D end_cc",
                {"ssh_import_id": ["smoser"], "runcmd": [["ls", "-l"]]},
            ),
            # Parse cmdlines that contain an IPv6 with cc: in different
            # positions
            ("BOOTIF=aa:bb:cc:dd bar", None),
            ("BOOTIF=aa:bb:cc:dd cc: end_cc bar", None),
            ("BOOTIF=aa:bb:cc:dd cc: ssh_pwauth: true", {"ssh_pwauth": True}),
            (
                "BOOTIF=aa:bb:cc:dd cc: ssh_pwauth: true end_cc",
                {"ssh_pwauth": True},
            ),
            (
                "cc: ssh_pwauth: true end_cc BOOTIF=aa:bb:cc:dd",
                {"ssh_pwauth": True},
            ),
        ],
    )
    def test_read_conf_from_cmdline_config(self, expected_cfg, cmdline):
        assert expected_cfg == util.read_conf_from_cmdline(cmdline=cmdline)


class TestMountCb:
    """Tests for ``util.mount_cb``.

    These tests consider the "unit" under test to be ``util.mount_cb`` and
    ``util.unmounter``, which is only used by ``mount_cb``.

    TODO: Test default mtype determination
    TODO: Test the if/else branch that actually performs the mounting operation
    """

    @pytest.fixture
    def already_mounted_device_and_mountdict(self):
        """Mock an already-mounted device, and yield (device, mount dict)"""
        device = "/dev/fake0"
        mountpoint = "/mnt/fake"
        with mock.patch(M_PATH + "subp.subp"):
            with mock.patch(M_PATH + "mounts") as m_mounts:
                mounts = {device: {"mountpoint": mountpoint}}
                m_mounts.return_value = mounts
                yield device, mounts[device]

    @pytest.fixture
    def already_mounted_device(self, already_mounted_device_and_mountdict):
        """already_mounted_device_and_mountdict, but return only the device"""
        return already_mounted_device_and_mountdict[0]

    @pytest.mark.parametrize(
        "mtype,expected",
        [
            # While the filesystem is called iso9660, the mount type is cd9660
            ("iso9660", "cd9660"),
            # vfat is generally called "msdos" on BSD
            ("vfat", "msdos"),
            # judging from man pages, only FreeBSD has this alias
            ("msdosfs", "msdos"),
            # Test happy path
            ("ufs", "ufs"),
        ],
    )
    @mock.patch(M_PATH + "is_Linux", autospec=True)
    @mock.patch(M_PATH + "is_BSD", autospec=True)
    @mock.patch(M_PATH + "subp.subp")
    @mock.patch("cloudinit.temp_utils.tempdir", autospec=True)
    def test_normalize_mtype_on_bsd(
        self, m_tmpdir, m_subp, m_is_BSD, m_is_Linux, mtype, expected
    ):
        m_is_BSD.return_value = True
        m_is_Linux.return_value = False
        m_tmpdir.return_value.__enter__ = mock.Mock(
            autospec=True, return_value="/tmp/fake"
        )
        m_tmpdir.return_value.__exit__ = mock.Mock(
            autospec=True, return_value=True
        )
        callback = mock.Mock(autospec=True)

        util.mount_cb("/dev/fake0", callback, mtype=mtype)
        assert (
            mock.call(
                [
                    "mount",
                    "-o",
                    "ro",
                    "-t",
                    expected,
                    "/dev/fake0",
                    "/tmp/fake",
                ],
                update_env=None,
            )
            in m_subp.call_args_list
        )

    @pytest.mark.parametrize("invalid_mtype", [int(0), float(0.0), dict()])
    def test_typeerror_raised_for_invalid_mtype(self, invalid_mtype):
        with pytest.raises(TypeError):
            util.mount_cb(mock.Mock(), mock.Mock(), mtype=invalid_mtype)

    @mock.patch(M_PATH + "subp.subp")
    def test_already_mounted_does_not_mount_or_umount_anything(
        self, m_subp, already_mounted_device
    ):
        util.mount_cb(already_mounted_device, mock.Mock())

        assert 0 == m_subp.call_count

    @pytest.mark.parametrize("trailing_slash_in_mounts", ["/", ""])
    def test_already_mounted_calls_callback(
        self, trailing_slash_in_mounts, already_mounted_device_and_mountdict
    ):
        device, mount_dict = already_mounted_device_and_mountdict
        mountpoint = mount_dict["mountpoint"]
        mount_dict["mountpoint"] += trailing_slash_in_mounts

        callback = mock.Mock()
        util.mount_cb(device, callback)

        # The mountpoint passed to callback should always have a trailing
        # slash, regardless of the input
        assert [mock.call(mountpoint + "/")] == callback.call_args_list

    def test_already_mounted_calls_callback_with_data(
        self, already_mounted_device
    ):
        callback = mock.Mock()
        util.mount_cb(
            already_mounted_device, callback, data=mock.sentinel.data
        )

        assert [
            mock.call(mock.ANY, mock.sentinel.data)
        ] == callback.call_args_list

    @pytest.mark.parametrize("log_error", [True, False])
    @mock.patch(M_PATH + "subp.subp")
    def test_mount_cb_log(self, m_subp, log_error, caplog):
        log_msg = (
            "Failed to mount device: '/dev/fake0' with type: "
            "'ntfs' using mount command:"
        )
        m_subp.side_effect = subp.ProcessExecutionError(
            "", "unknown filesystem type 'ntfs'"
        )
        callback = mock.Mock(autospec=True)
        with pytest.raises(Exception):
            util.mount_cb(
                "/dev/fake0",
                callback,
                mtype="ntfs",
                update_env_for_mount={"LANG": "C"},
                log_error=log_error,
            )
        if log_error:
            assert log_msg in caplog.text
        else:
            assert log_msg not in caplog.text


@mock.patch(M_PATH + "write_file")
class TestEnsureFile:
    """Tests for ``cloudinit.util.ensure_file``."""

    def test_parameters_passed_through(self, m_write_file):
        """Test the parameters in the signature are passed to write_file."""
        util.ensure_file(
            mock.sentinel.path,
            mode=mock.sentinel.mode,
            preserve_mode=mock.sentinel.preserve_mode,
        )

        assert 1 == m_write_file.call_count
        args, kwargs = m_write_file.call_args
        assert (mock.sentinel.path,) == args
        assert mock.sentinel.mode == kwargs["mode"]
        assert mock.sentinel.preserve_mode == kwargs["preserve_mode"]

    @pytest.mark.parametrize(
        "kwarg,expected",
        [
            # Files should be world-readable by default
            ("mode", 0o644),
            # The previous behaviour of not preserving mode should be retained
            ("preserve_mode", False),
        ],
    )
    def test_defaults(self, m_write_file, kwarg, expected):
        """Test that ensure_file defaults appropriately."""
        util.ensure_file(mock.sentinel.path)

        assert 1 == m_write_file.call_count
        _args, kwargs = m_write_file.call_args
        assert expected == kwargs[kwarg]

    def test_static_parameters_are_passed(self, m_write_file):
        """Test that the static write_files parameters are passed correctly."""
        util.ensure_file(mock.sentinel.path)

        assert 1 == m_write_file.call_count
        _args, kwargs = m_write_file.call_args
        assert "" == kwargs["content"]
        assert "ab" == kwargs["omode"]


@mock.patch(M_PATH + "grp.getgrnam")
@mock.patch(M_PATH + "os.setgid")
@mock.patch(M_PATH + "os.umask")
class TestRedirectOutputPreexecFn:
    """This tests specifically the preexec_fn used in redirect_output."""

    @pytest.fixture(params=["outfmt", "errfmt"])
    def preexec_fn(self, request):
        """A fixture to gather the preexec_fn used by redirect_output.

        This enables simpler direct testing of it, and parameterises any tests
        using it to cover both the stdout and stderr code paths.
        """
        test_string = "| piped output to invoke subprocess"
        if request.param == "outfmt":
            args = (test_string, None)
        elif request.param == "errfmt":
            args = (None, test_string)
        else:
            args = (None, None)
        with mock.patch(M_PATH + "subprocess.Popen") as m_popen:
            util.redirect_output(*args)

        assert 1 == m_popen.call_count
        _args, kwargs = m_popen.call_args
        assert "preexec_fn" in kwargs, "preexec_fn not passed to Popen"
        return kwargs["preexec_fn"]

    def test_preexec_fn_sets_umask(
        self, m_os_umask, _m_setgid, _m_getgrnam, preexec_fn
    ):
        """preexec_fn should set a mask that avoids world-readable files."""
        preexec_fn()

        assert [mock.call(0o037)] == m_os_umask.call_args_list

    def test_preexec_fn_sets_group_id_if_adm_group_present(
        self, _m_os_umask, m_setgid, m_getgrnam, preexec_fn
    ):
        """We should setgrp to adm if present, so files are owned by them."""
        fake_group = mock.Mock(gr_gid=mock.sentinel.gr_gid)
        m_getgrnam.return_value = fake_group

        preexec_fn()

        assert [mock.call("adm")] == m_getgrnam.call_args_list
        assert [mock.call(mock.sentinel.gr_gid)] == m_setgid.call_args_list

    def test_preexec_fn_handles_absent_adm_group_gracefully(
        self, _m_os_umask, m_setgid, m_getgrnam, preexec_fn
    ):
        """We should handle an absent adm group gracefully."""
        m_getgrnam.side_effect = KeyError("getgrnam(): name not found: 'adm'")

        preexec_fn()

        assert 0 == m_setgid.call_count


class FakeSelinux:
    def __init__(self, match_what):
        self.match_what = match_what
        self.restored = []

    def matchpathcon(self, path, mode):
        if path == self.match_what:
            return
        else:
            raise OSError("No match!")

    def is_selinux_enabled(self):
        return True

    def restorecon(self, path, recursive):
        self.restored.append(path)


class TestGetCfgOptionListOrStr(helpers.TestCase):
    def test_not_found_no_default(self):
        """None is returned if key is not found and no default given."""
        config = {}
        result = util.get_cfg_option_list(config, "key")
        self.assertIsNone(result)

    def test_not_found_with_default(self):
        """Default is returned if key is not found."""
        config = {}
        result = util.get_cfg_option_list(config, "key", default=["DEFAULT"])
        self.assertEqual(["DEFAULT"], result)

    def test_found_with_default(self):
        """Default is not returned if key is found."""
        config = {"key": ["value1"]}
        result = util.get_cfg_option_list(config, "key", default=["DEFAULT"])
        self.assertEqual(["value1"], result)

    def test_found_convert_to_list(self):
        """Single string is converted to one element list."""
        config = {"key": "value1"}
        result = util.get_cfg_option_list(config, "key")
        self.assertEqual(["value1"], result)

    def test_value_is_none(self):
        """If value is None empty list is returned."""
        config = {"key": None}
        result = util.get_cfg_option_list(config, "key")
        self.assertEqual([], result)


class TestWriteFile(helpers.TestCase):
    def setUp(self):
        super(TestWriteFile, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_basic_usage(self):
        """Verify basic usage with default args."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            create_contents = f.read()
            self.assertEqual(contents, create_contents)
        file_stat = os.stat(path)
        self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))

    def test_dir_is_created_if_required(self):
        """Verifiy that directories are created is required."""
        dirname = os.path.join(self.tmp, "subdir")
        path = os.path.join(dirname, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents)

        self.assertTrue(os.path.isdir(dirname))
        self.assertTrue(os.path.isfile(path))

    def test_dir_ownership(self):
        """Verifiy that directories is created with appropriate ownership."""
        dirname = os.path.join(self.tmp, "subdir", "subdir2")
        path = os.path.join(dirname, "NewFile.txt")
        contents = "Hey there"
        user = "foo"
        group = "foo"

        with mock.patch.object(
            util, "chownbyname", return_value=None
        ) as mockobj:
            util.write_file(path, contents, user=user, group=group)

        calls = [
            mock.call(os.path.join(self.tmp, "subdir"), user, group),
            mock.call(Path(dirname), user, group),
        ]
        mockobj.assert_has_calls(calls, any_order=False)

    def test_dir_is_not_created_if_ensure_dir_false(self):
        """Verify directories are not created if ensure_dir_exists is False."""
        dirname = os.path.join(self.tmp, "subdir")
        path = os.path.join(dirname, "NewFile.txt")
        contents = "Hey there"

        with self.assertRaises(FileNotFoundError):
            util.write_file(path, contents, ensure_dir_exists=False)

        self.assertFalse(os.path.isdir(dirname))

    def test_explicit_mode(self):
        """Verify explicit file mode works properly."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents, mode=0o666)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        file_stat = os.stat(path)
        self.assertEqual(0o666, stat.S_IMODE(file_stat.st_mode))

    def test_preserve_mode_no_existing(self):
        """Verify that file is created with mode 0o644 if preserve_mode
        is true and there is no prior existing file."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        util.write_file(path, contents, preserve_mode=True)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        file_stat = os.stat(path)
        self.assertEqual(0o644, stat.S_IMODE(file_stat.st_mode))

    def test_preserve_mode_with_existing(self):
        """Verify that file is created using mode of existing file
        if preserve_mode is true."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        open(path, "w").close()
        os.chmod(path, 0o666)

        util.write_file(path, contents, preserve_mode=True)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        file_stat = os.stat(path)
        self.assertEqual(0o666, stat.S_IMODE(file_stat.st_mode))

    def test_custom_omode(self):
        """Verify custom omode works properly."""
        path = os.path.join(self.tmp, "NewFile.txt")
        contents = "Hey there"

        # Create file first with basic content
        with open(path, "wb") as f:
            f.write(b"LINE1\n")
        util.write_file(path, contents, omode="a")

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.isfile(path))
        with open(path) as f:
            create_contents = f.read()
            self.assertEqual("LINE1\nHey there", create_contents)

    def test_restorecon_if_possible_is_called(self):
        """Make sure the selinux guard is called correctly."""
        my_file = os.path.join(self.tmp, "my_file")
        with open(my_file, "w") as fp:
            fp.write("My Content")

        fake_se = FakeSelinux(my_file)

        with mock.patch.object(
            importer, "import_module", return_value=fake_se
        ) as mockobj:
            with util.SeLinuxGuard(my_file) as is_on:
                self.assertTrue(is_on)

        self.assertEqual(1, len(fake_se.restored))
        self.assertEqual(my_file, fake_se.restored[0])

        mockobj.assert_called_once_with("selinux")


class TestDeleteDirContents(helpers.TestCase):
    def setUp(self):
        super(TestDeleteDirContents, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def assertDirEmpty(self, dirname):
        self.assertEqual([], os.listdir(dirname))

    def test_does_not_delete_dir(self):
        """Ensure directory itself is not deleted."""
        util.delete_dir_contents(self.tmp)

        self.assertTrue(os.path.isdir(self.tmp))
        self.assertDirEmpty(self.tmp)

    def test_deletes_files(self):
        """Single file should be deleted."""
        with open(os.path.join(self.tmp, "new_file.txt"), "wb") as f:
            f.write(b"DELETE ME")

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_empty_dirs(self):
        """Empty directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_nested_dirs(self):
        """Nested directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))
        os.mkdir(os.path.join(self.tmp, "new_dir", "new_subdir"))

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_non_empty_dirs(self):
        """Non-empty directories should be deleted."""
        os.mkdir(os.path.join(self.tmp, "new_dir"))
        f_name = os.path.join(self.tmp, "new_dir", "new_file.txt")
        with open(f_name, "wb") as f:
            f.write(b"DELETE ME")

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)

    def test_deletes_symlinks(self):
        """Symlinks should be deleted."""
        file_name = os.path.join(self.tmp, "new_file.txt")
        link_name = os.path.join(self.tmp, "new_file_link.txt")
        with open(file_name, "wb") as f:
            f.write(b"DELETE ME")
        os.symlink(file_name, link_name)

        util.delete_dir_contents(self.tmp)

        self.assertDirEmpty(self.tmp)


class TestKeyValStrings(helpers.TestCase):
    def test_keyval_str_to_dict(self):
        expected = {"1": "one", "2": "one+one", "ro": True}
        cmdline = "1=one ro 2=one+one"
        self.assertEqual(expected, util.keyval_str_to_dict(cmdline))


class TestGetCmdline(helpers.TestCase):
    def test_cmdline_reads_debug_env(self):
        with mock.patch.dict(
            "os.environ", values={"DEBUG_PROC_CMDLINE": "abcd 123"}
        ):
            ret = util.get_cmdline()
        self.assertEqual("abcd 123", ret)


class TestFipsEnabled:
    @pytest.mark.parametrize(
        "fips_enabled_content,expected",
        (
            pytest.param(None, False, id="false_when_no_fips_enabled_file"),
            pytest.param("0\n", False, id="false_when_fips_disabled"),
            pytest.param("1\n", True, id="true_when_fips_enabled"),
            pytest.param("1", True, id="true_when_fips_enabled_no_newline"),
        ),
    )
    @mock.patch(M_PATH + "load_text_file")
    def test_fips_enabled_based_on_proc_crypto(
        self, load_file, fips_enabled_content, expected, tmpdir
    ):
        def fake_load_file(path):
            assert path == "/proc/sys/crypto/fips_enabled"
            if fips_enabled_content is None:
                raise IOError("No file exists Bob")
            return fips_enabled_content

        load_file.side_effect = fake_load_file

        assert expected is util.fips_enabled()


class TestLoadYaml(helpers.CiTestCase):
    mydefault = "7b03a8ebace993d806255121073fed52"
    with_logs = True

    def test_simple(self):
        mydata = {"1": "one", "2": "two"}
        self.assertEqual(util.load_yaml(yaml.dump(mydata)), mydata)

    def test_nonallowed_returns_default(self):
        """Any unallowed types result in returning default; log the issue."""
        # for now, anything not in the allowed list just returns the default.
        myyaml = yaml.dump({"1": "one"})
        self.assertEqual(
            util.load_yaml(
                blob=myyaml, default=self.mydefault, allowed=(str,)
            ),
            self.mydefault,
        )
        regex = re.compile(
            r"Yaml load allows \(<(class|type) \'str\'>,\) root types, but"
            r" got dict"
        )
        self.assertTrue(
            regex.search(self.logs.getvalue()),
            msg="Missing expected yaml load error",
        )

    def test_bogus_scan_error_returns_default(self):
        """On Yaml scan error, load_yaml returns the default and logs issue."""
        badyaml = "1\n 2:"
        self.assertEqual(
            util.load_yaml(blob=badyaml, default=self.mydefault),
            self.mydefault,
        )
        self.assertIn(
            "Failed loading yaml blob. Invalid format at line 2 column 3:"
            ' "mapping values are not allowed here',
            self.logs.getvalue(),
        )

    def test_bogus_parse_error_returns_default(self):
        """On Yaml parse error, load_yaml returns default and logs issue."""
        badyaml = "{}}"
        self.assertEqual(
            util.load_yaml(blob=badyaml, default=self.mydefault),
            self.mydefault,
        )
        self.assertIn(
            "Failed loading yaml blob. Invalid format at line 1 column 3:"
            " \"expected '<document start>', but found '}'",
            self.logs.getvalue(),
        )

    def test_unsafe_types(self):
        # should not load complex types
        unsafe_yaml = yaml.dump(
            (
                1,
                2,
                3,
            )
        )
        self.assertEqual(
            util.load_yaml(blob=unsafe_yaml, default=self.mydefault),
            self.mydefault,
        )

    def test_python_unicode(self):
        # complex type of python/unicode is explicitly allowed
        myobj = {"1": "FOOBAR"}
        safe_yaml = yaml.dump(myobj)
        self.assertEqual(
            util.load_yaml(blob=safe_yaml, default=self.mydefault), myobj
        )

    def test_none_returns_default(self):
        """If yaml.load returns None, then default should be returned."""
        blobs = ("", " ", "# foo\n", "#")
        mdef = self.mydefault
        self.assertEqual(
            [(b, self.mydefault) for b in blobs],
            [(b, util.load_yaml(blob=b, default=mdef)) for b in blobs],
        )


class TestMountinfoParsing(helpers.ResourceUsingTestCase):
    def test_invalid_mountinfo(self):
        line = (
            "20 1 252:1 / / rw,relatime - ext4 /dev/mapper/vg0-root"
            "rw,errors=remount-ro,data=ordered"
        )
        elements = line.split()
        for i in range(len(elements) + 1):
            lines = [" ".join(elements[0:i])]
            if i < 10:
                expected = None
            else:
                expected = ("/dev/mapper/vg0-root", "ext4", "/")
            self.assertEqual(expected, util.parse_mount_info("/", lines))

    def test_precise_ext4_root(self):
        lines = helpers.readResource("mountinfo_precise_ext4.txt").splitlines()

        expected = ("/dev/mapper/vg0-root", "ext4", "/")
        self.assertEqual(expected, util.parse_mount_info("/", lines))
        self.assertEqual(expected, util.parse_mount_info("/usr", lines))
        self.assertEqual(expected, util.parse_mount_info("/usr/bin", lines))

        expected = ("/dev/md0", "ext4", "/boot")
        self.assertEqual(expected, util.parse_mount_info("/boot", lines))
        self.assertEqual(expected, util.parse_mount_info("/boot/grub", lines))

        expected = ("/dev/mapper/vg0-root", "ext4", "/")
        self.assertEqual(expected, util.parse_mount_info("/home", lines))
        self.assertEqual(expected, util.parse_mount_info("/home/me", lines))

        expected = ("tmpfs", "tmpfs", "/run")
        self.assertEqual(expected, util.parse_mount_info("/run", lines))

        expected = ("none", "tmpfs", "/run/lock")
        self.assertEqual(expected, util.parse_mount_info("/run/lock", lines))

    def test_raring_btrfs_root(self):
        lines = helpers.readResource("mountinfo_raring_btrfs.txt").splitlines()

        expected = ("/dev/vda1", "btrfs", "/")
        self.assertEqual(expected, util.parse_mount_info("/", lines))
        self.assertEqual(expected, util.parse_mount_info("/usr", lines))
        self.assertEqual(expected, util.parse_mount_info("/usr/bin", lines))
        self.assertEqual(expected, util.parse_mount_info("/boot", lines))
        self.assertEqual(expected, util.parse_mount_info("/boot/grub", lines))

        expected = ("/dev/vda1", "btrfs", "/home")
        self.assertEqual(expected, util.parse_mount_info("/home", lines))
        self.assertEqual(expected, util.parse_mount_info("/home/me", lines))

        expected = ("tmpfs", "tmpfs", "/run")
        self.assertEqual(expected, util.parse_mount_info("/run", lines))

        expected = ("none", "tmpfs", "/run/lock")
        self.assertEqual(expected, util.parse_mount_info("/run/lock", lines))

    @mock.patch("cloudinit.subp.subp")
    def test_parse_mount_with_ext(self, mount_out):
        mount_out.return_value = (
            helpers.readResource("mount_parse_ext.txt"),
            "",
        )
        # this one is valid and exists in mount_parse_ext.txt
        ret = util.parse_mount("/var")
        self.assertEqual(("/dev/mapper/vg00-lv_var", "ext4", "/var"), ret)
        # another one that is valid and exists
        ret = util.parse_mount("/")
        self.assertEqual(("/dev/mapper/vg00-lv_root", "ext4", "/"), ret)
        # this one exists in mount_parse_ext.txt
        ret = util.parse_mount("/sys/kernel/debug")
        self.assertEqual(("none", "debugfs", "/sys/kernel/debug"), ret)
        # this one does not exist in mount_parse_ext.txt
        ret = util.parse_mount("/var/tmp/cloud-init")
        self.assertEqual(("/dev/mapper/vg00-lv_var", "ext4", "/var"), ret)

    @mock.patch("cloudinit.subp.subp")
    def test_parse_mount_with_zfs(self, mount_out):
        mount_out.return_value = (
            helpers.readResource("mount_parse_zfs.txt"),
            "",
        )
        # this one is valid and exists in mount_parse_zfs.txt
        ret = util.parse_mount("/var")
        self.assertEqual(("vmzroot/ROOT/freebsd/var", "zfs", "/var"), ret)
        # this one is the root, valid and also exists in mount_parse_zfs.txt
        ret = util.parse_mount("/")
        self.assertEqual(("vmzroot/ROOT/freebsd", "zfs", "/"), ret)
        # this one does not exist in mount_parse_ext.txt
        ret = util.parse_mount("/var/tmp/cloud-init")
        self.assertEqual(("vmzroot/var/tmp", "zfs", "/var/tmp"), ret)


class TestIsX86(helpers.CiTestCase):
    def test_is_x86_matches_x86_types(self):
        """is_x86 returns True if CPU architecture matches."""
        matched_arches = ["x86_64", "i386", "i586", "i686"]
        for arch in matched_arches:
            self.assertTrue(
                util.is_x86(arch), 'Expected is_x86 for arch "%s"' % arch
            )

    def test_is_x86_unmatched_types(self):
        """is_x86 returns Fale on non-intel x86 architectures."""
        unmatched_arches = ["ia64", "9000/800", "arm64v71"]
        for arch in unmatched_arches:
            self.assertFalse(
                util.is_x86(arch), 'Expected not is_x86 for arch "%s"' % arch
            )

    @mock.patch(M_PATH + "os.uname")
    def test_is_x86_calls_uname_for_architecture(self, m_uname):
        """is_x86 returns True if platform from uname matches."""
        m_uname.return_value = [0, 1, 2, 3, "x86_64"]
        self.assertTrue(util.is_x86())


class TestGetConfigLogfiles(helpers.CiTestCase):
    def test_empty_cfg_returns_empty_list(self):
        """An empty config passed to get_config_logfiles returns empty list."""
        self.assertEqual([], util.get_config_logfiles(None))
        self.assertEqual([], util.get_config_logfiles({}))

    def test_default_log_file_present(self):
        """When default_log_file is set get_config_logfiles finds it."""
        self.assertEqual(
            ["/my.log"], util.get_config_logfiles({"def_log_file": "/my.log"})
        )

    def test_output_logs_parsed_when_teeing_files(self):
        """When output configuration is parsed when teeing files."""
        self.assertEqual(
            ["/himom.log", "/my.log"],
            sorted(
                util.get_config_logfiles(
                    {
                        "def_log_file": "/my.log",
                        "output": {"all": "|tee -a /himom.log"},
                    }
                )
            ),
        )

    def test_output_logs_parsed_when_redirecting(self):
        """When output configuration is parsed when redirecting to a file."""
        self.assertEqual(
            ["/my.log", "/test.log"],
            sorted(
                util.get_config_logfiles(
                    {
                        "def_log_file": "/my.log",
                        "output": {"all": ">/test.log"},
                    }
                )
            ),
        )

    def test_output_logs_parsed_when_appending(self):
        """When output configuration is parsed when appending to a file."""
        self.assertEqual(
            ["/my.log", "/test.log"],
            sorted(
                util.get_config_logfiles(
                    {
                        "def_log_file": "/my.log",
                        "output": {"all": ">> /test.log"},
                    }
                )
            ),
        )

    def test_output_logs_parsed_when_teeing_files_and_rotated(self):
        """When output configuration is parsed when teeing files and rotated
        log files are present."""
        tmpd = self.tmp_dir()
        log1 = self.tmp_path("my.log", tmpd)
        log1_rotated = self.tmp_path("my.log.1.gz", tmpd)
        log2 = self.tmp_path("himom.log", tmpd)
        log2_rotated = self.tmp_path("himom.log.1.gz", tmpd)

        util.write_file(log1_rotated, "hello")
        util.write_file(log2_rotated, "hello")

        self.assertEqual(
            [log2, log2_rotated, log1, log1_rotated],
            sorted(
                util.get_config_logfiles(
                    {
                        "def_log_file": str(log1),
                        "output": {"all": f"|tee -a {log2}"},
                    }
                )
            ),
        )


class TestMultiLog(helpers.FilesystemMockingTestCase):
    def _createConsole(self, root):
        os.mkdir(os.path.join(root, "dev"))
        open(os.path.join(root, "dev", "console"), "a").close()

    def setUp(self):
        super(TestMultiLog, self).setUp()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.patchOS(self.root)
        self.patchUtils(self.root)
        self.patchOpen(self.root)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.patchStdoutAndStderr(self.stdout, self.stderr)

    def test_stderr_used_by_default(self):
        logged_string = "test stderr output"
        util.multi_log(logged_string)
        self.assertEqual(logged_string, self.stderr.getvalue())

    def test_stderr_not_used_if_false(self):
        util.multi_log("should not see this", stderr=False)
        self.assertEqual("", self.stderr.getvalue())

    def test_logs_go_to_console_by_default(self):
        self._createConsole(self.root)
        logged_string = "something very important"
        util.multi_log(logged_string)
        with open("/dev/console") as f:
            self.assertEqual(logged_string, f.read())

    def test_logs_dont_go_to_stdout_if_console_exists(self):
        self._createConsole(self.root)
        util.multi_log("something")
        self.assertEqual("", self.stdout.getvalue())

    def test_logs_go_to_stdout_if_console_does_not_exist(self):
        logged_string = "something very important"
        util.multi_log(logged_string)
        self.assertEqual(logged_string, self.stdout.getvalue())

    def test_logs_dont_go_to_stdout_if_fallback_to_stdout_is_false(self):
        util.multi_log("something", fallback_to_stdout=False)
        self.assertEqual("", self.stdout.getvalue())

    @mock.patch(
        M_PATH + "write_to_console",
        mock.Mock(side_effect=OSError("Failed to write to console")),
    )
    def test_logs_go_to_stdout_if_writing_to_console_fails_and_fallback_true(
        self,
    ):
        self._createConsole(self.root)
        util.multi_log("something", fallback_to_stdout=True)
        self.assertEqual(
            "Failed to write to /dev/console\nsomething",
            self.stdout.getvalue(),
        )

    @mock.patch(
        M_PATH + "write_to_console",
        mock.Mock(side_effect=OSError("Failed to write to console")),
    )
    def test_logs_go_nowhere_if_writing_to_console_fails_and_fallback_false(
        self,
    ):
        self._createConsole(self.root)
        util.multi_log("something", fallback_to_stdout=False)
        self.assertEqual(
            "Failed to write to /dev/console\n", self.stdout.getvalue()
        )

    def test_logs_go_to_log_if_given(self):
        log = mock.MagicMock()
        logged_string = "something very important"
        util.multi_log(logged_string, log=log)
        self.assertEqual(
            [((mock.ANY, logged_string), {})], log.log.call_args_list
        )

    def test_newlines_stripped_from_log_call(self):
        log = mock.MagicMock()
        expected_string = "something very important"
        util.multi_log("{0}\n".format(expected_string), log=log)
        self.assertEqual((mock.ANY, expected_string), log.log.call_args[0])

    def test_log_level_defaults_to_debug(self):
        log = mock.MagicMock()
        util.multi_log("message", log=log)
        self.assertEqual((logging.DEBUG, mock.ANY), log.log.call_args[0])

    def test_given_log_level_used(self):
        log = mock.MagicMock()
        log_level = mock.Mock()
        util.multi_log("message", log=log, log_level=log_level)
        self.assertEqual((log_level, mock.ANY), log.log.call_args[0])


class TestMessageFromString(helpers.TestCase):
    def test_unicode_not_messed_up(self):
        roundtripped = util.message_from_string("\n").as_string()
        self.assertNotIn("\x00", roundtripped)


class TestReadSeeded:
    def test_unicode_not_messed_up(self, tmpdir):
        ud = b"userdatablob"
        vd = b"vendordatablob"
        helpers.populate_dir(
            tmpdir.strpath,
            {"meta-data": "key1: val1", "user-data": ud, "vendor-data": vd},
        )
        (found_md, found_ud, found_vd) = util.read_seeded(
            tmpdir.strpath + os.path.sep
        )
        assert found_md == {"key1": "val1"}
        assert found_ud == ud
        assert found_vd == vd

    @pytest.mark.parametrize(
        "base, feature_flag, req_urls",
        (
            pytest.param(
                "http://10.0.0.1/%s?qs=1",
                True,
                [
                    "http://10.0.0.1/meta-data?qs=1",
                    "http://10.0.0.1/user-data?qs=1",
                    "http://10.0.0.1/vendor-data?qs=1",
                ],
                id="expand_percent_s_to_data_route",
            ),
            pytest.param(
                "https://10.0.0.1:8008/",
                True,
                [
                    "https://10.0.0.1:8008/meta-data",
                    "https://10.0.0.1:8008/user-data",
                    "https://10.0.0.1:8008/vendor-data",
                ],
                id="no_duplicate_forward_slash_when_already_present",
            ),
            pytest.param(
                "https://10.0.0.1:8008",
                True,
                [
                    "https://10.0.0.1:8008/meta-data",
                    "https://10.0.0.1:8008/user-data",
                    "https://10.0.0.1:8008/vendor-data",
                ],
                id="append_fwd_slash_on_routes_when_absent_and_no_query_str",
            ),
            pytest.param(
                "https://10.0.0.1:8008",
                False,
                [
                    "https://10.0.0.1:8008meta-data",
                    "https://10.0.0.1:8008user-data",
                    "https://10.0.0.1:8008vendor-data",
                ],
                id="feature_off_append_fwd_slash_when_absent_and_no_query_str",
            ),
            pytest.param(
                "https://10.0.0.1:8008?qs=",
                True,
                [
                    "https://10.0.0.1:8008?qs=meta-data",
                    "https://10.0.0.1:8008?qs=user-data",
                    "https://10.0.0.1:8008?qs=vendor-data",
                ],
                id="avoid_trailing_forward_slash_on_routes_with_query_strings",
            ),
        ),
    )
    @mock.patch(M_PATH + "url_helper.read_file_or_url")
    def test_handle_http_urls(
        self, m_read, base, feature_flag, req_urls, tmpdir
    ):
        def fake_response(url, timeout, retries):
            parsed_url = urlparse(url)
            path = parsed_url.path
            if not path:
                if parsed_url.query:
                    _key, _, md_type = parsed_url.query.partition("=")
                else:
                    _url, _, md_type = parsed_url.netloc.partition("8008")
                path = f"/{md_type}"
            return url_helper.StringResponse(f"{path}: 1", "http://url/")

        m_read.side_effect = fake_response

        with mock.patch.object(
            features,
            "NOCLOUD_SEED_URL_APPEND_FORWARD_SLASH",
            feature_flag,
        ):
            (found_md, found_ud, found_vd) = util.read_seeded(base)
        # Meta-data treated as YAML
        assert found_md == {"/meta-data": 1}
        # user-data, vendor-data read raw. It could be scripts or other format
        assert found_ud == "/user-data: 1"
        assert found_vd == "/vendor-data: 1"
        assert [
            mock.call(req_url, timeout=5, retries=10) for req_url in req_urls
        ] == m_read.call_args_list


class TestReadSeededWithoutVendorData(helpers.TestCase):
    def setUp(self):
        super(TestReadSeededWithoutVendorData, self).setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_unicode_not_messed_up(self):
        ud = b"userdatablob"
        vd = None
        helpers.populate_dir(
            self.tmp, {"meta-data": "key1: val1", "user-data": ud}
        )
        sdir = self.tmp + os.path.sep
        (found_md, found_ud, found_vd) = util.read_seeded(sdir)

        self.assertEqual(found_md, {"key1": "val1"})
        self.assertEqual(found_ud, ud)
        self.assertEqual(found_vd, vd)


class TestEncode(helpers.TestCase):
    """Test the encoding functions"""

    def test_decode_binary_plain_text_with_hex(self):
        blob = "BOOTABLE_FLAG=\x80init=/bin/systemd"
        text = util.decode_binary(blob)
        self.assertEqual(text, blob)


class TestProcessExecutionError(helpers.TestCase):
    template = (
        "{description}\n"
        "Command: {cmd}\n"
        "Exit code: {exit_code}\n"
        "Reason: {reason}\n"
        "Stdout: {stdout}\n"
        "Stderr: {stderr}"
    )
    empty_attr = "-"
    empty_description = "Unexpected error while running command."

    def test_pexec_error_indent_text(self):
        error = subp.ProcessExecutionError()
        msg = "abc\ndef"
        formatted = "abc\n{0}def".format(" " * 4)
        self.assertEqual(error._indent_text(msg, indent_level=4), formatted)
        self.assertEqual(
            error._indent_text(msg.encode(), indent_level=4),
            formatted.encode(),
        )
        self.assertIsInstance(
            error._indent_text(msg.encode()), type(msg.encode())
        )

    def test_pexec_error_type(self):
        self.assertIsInstance(subp.ProcessExecutionError(), IOError)

    def test_pexec_error_empty_msgs(self):
        error = subp.ProcessExecutionError()
        self.assertTrue(
            all(
                attr == self.empty_attr
                for attr in (error.stderr, error.stdout, error.reason)
            )
        )
        self.assertEqual(error.description, self.empty_description)
        self.assertEqual(
            str(error),
            self.template.format(
                description=self.empty_description,
                exit_code=self.empty_attr,
                reason=self.empty_attr,
                stdout=self.empty_attr,
                stderr=self.empty_attr,
                cmd=self.empty_attr,
            ),
        )

    def test_pexec_error_single_line_msgs(self):
        stdout_msg = "out out"
        stderr_msg = "error error"
        cmd = "test command"
        exit_code = 3
        error = subp.ProcessExecutionError(
            stdout=stdout_msg, stderr=stderr_msg, exit_code=3, cmd=cmd
        )
        self.assertEqual(
            str(error),
            self.template.format(
                description=self.empty_description,
                stdout=stdout_msg,
                stderr=stderr_msg,
                exit_code=str(exit_code),
                reason=self.empty_attr,
                cmd=cmd,
            ),
        )

    def test_pexec_error_multi_line_msgs(self):
        # make sure bytes is converted handled properly when formatting
        stdout_msg = "multi\nline\noutput message".encode()
        stderr_msg = "multi\nline\nerror message\n\n\n"
        error = subp.ProcessExecutionError(
            stdout=stdout_msg, stderr=stderr_msg
        )
        self.assertEqual(
            str(error),
            "\n".join(
                (
                    "{description}",
                    "Command: {empty_attr}",
                    "Exit code: {empty_attr}",
                    "Reason: {empty_attr}",
                    "Stdout: multi",
                    "        line",
                    "        output message",
                    "Stderr: multi",
                    "        line",
                    "        error message",
                )
            ).format(
                description=self.empty_description, empty_attr=self.empty_attr
            ),
        )


class TestSystemIsSnappy(helpers.FilesystemMockingTestCase):
    def test_id_in_os_release_quoted(self):
        """os-release containing ID="ubuntu-core" is snappy."""
        orcontent = "\n".join(['ID="ubuntu-core"', ""])
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {"etc/os-release": orcontent})
        self.reRoot(root_d)
        self.assertTrue(util.system_is_snappy())

    def test_id_in_os_release(self):
        """os-release containing ID=ubuntu-core is snappy."""
        orcontent = "\n".join(["ID=ubuntu-core", ""])
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {"etc/os-release": orcontent})
        self.reRoot(root_d)
        self.assertTrue(util.system_is_snappy())

    @mock.patch(M_PATH + "get_cmdline")
    def test_bad_content_in_os_release_no_effect(self, m_cmdline):
        """malformed os-release should not raise exception."""
        m_cmdline.return_value = "root=/dev/sda"
        orcontent = "\n".join(["IDubuntu-core", ""])
        root_d = self.tmp_dir()
        helpers.populate_dir(root_d, {"etc/os-release": orcontent})
        self.reRoot()
        self.assertFalse(util.system_is_snappy())

    @mock.patch(M_PATH + "get_cmdline")
    def test_snap_core_in_cmdline_is_snappy(self, m_cmdline):
        """The string snap_core= in kernel cmdline indicates snappy."""
        cmdline = (
            "BOOT_IMAGE=(loop)/kernel.img root=LABEL=writable "
            "snap_core=core_x1.snap snap_kernel=pc-kernel_x1.snap ro "
            "net.ifnames=0 init=/lib/systemd/systemd console=tty1 "
            "console=ttyS0 panic=-1"
        )
        m_cmdline.return_value = cmdline
        self.assertTrue(util.system_is_snappy())
        self.assertTrue(m_cmdline.call_count > 0)

    @mock.patch(M_PATH + "get_cmdline")
    def test_nothing_found_is_not_snappy(self, m_cmdline):
        """If no positive identification, then not snappy."""
        m_cmdline.return_value = "root=/dev/sda"
        self.reRoot()
        self.assertFalse(util.system_is_snappy())
        self.assertTrue(m_cmdline.call_count > 0)

    @mock.patch(M_PATH + "get_cmdline")
    def test_channel_ini_with_snappy_is_snappy(self, m_cmdline):
        """A Channel.ini file with 'ubuntu-core' indicates snappy."""
        m_cmdline.return_value = "root=/dev/sda"
        root_d = self.tmp_dir()
        content = "\n".join(["[Foo]", "source = 'ubuntu-core'", ""])
        helpers.populate_dir(root_d, {"etc/system-image/channel.ini": content})
        self.reRoot(root_d)
        self.assertTrue(util.system_is_snappy())

    @mock.patch(M_PATH + "get_cmdline")
    def test_system_image_config_dir_is_snappy(self, m_cmdline):
        """Existence of /etc/system-image/config.d indicates snappy."""
        m_cmdline.return_value = "root=/dev/sda"
        root_d = self.tmp_dir()
        helpers.populate_dir(
            root_d, {"etc/system-image/config.d/my.file": "_unused"}
        )
        self.reRoot(root_d)
        self.assertTrue(util.system_is_snappy())


class TestLoadShellContent(helpers.TestCase):
    def test_comments_handled_correctly(self):
        """Shell comments should be allowed in the content."""
        self.assertEqual(
            {"key1": "val1", "key2": "val2", "key3": "val3 #tricky"},
            util.load_shell_content(
                "\n".join(
                    [
                        "#top of file comment",
                        "key1=val1 #this is a comment",
                        "# second comment",
                        'key2="val2" # inlin comment#badkey=wark',
                        'key3="val3 #tricky"',
                        "",
                    ]
                )
            ),
        )


@skipIf(
    not util.is_Linux(), "These tests don't make sense on non-Linux systems."
)
class TestGetProcEnv(helpers.TestCase):
    """test get_proc_env."""

    null = b"\x00"
    simple1 = b"HOME=/"
    simple2 = b"PATH=/bin:/sbin"
    bootflag = b"BOOTABLE_FLAG=\x80"  # from LP: #1775371
    mixed = b"MIXED=" + b"ab\xccde"

    def _val_decoded(self, blob, encoding="utf-8", errors="replace"):
        # return the value portion of key=val decoded.
        return blob.split(b"=", 1)[1].decode(encoding, errors)

    @mock.patch(M_PATH + "load_binary_file")
    def test_non_utf8_in_environment(self, m_load_file):
        """env may have non utf-8 decodable content."""
        content = self.null.join(
            (self.bootflag, self.simple1, self.simple2, self.mixed)
        )
        m_load_file.return_value = content

        self.assertEqual(
            {
                "BOOTABLE_FLAG": self._val_decoded(self.bootflag),
                "HOME": "/",
                "PATH": "/bin:/sbin",
                "MIXED": self._val_decoded(self.mixed),
            },
            util.get_proc_env(1),
        )
        self.assertEqual(1, m_load_file.call_count)

    @mock.patch(M_PATH + "load_binary_file")
    def test_encoding_none_returns_bytes(self, m_load_file):
        """encoding none returns bytes."""
        lines = (self.bootflag, self.simple1, self.simple2, self.mixed)
        content = self.null.join(lines)
        m_load_file.return_value = content

        self.assertEqual(
            dict([t.split(b"=") for t in lines]),
            util.get_proc_env(1, encoding=None),
        )
        self.assertEqual(1, m_load_file.call_count)

    @mock.patch(M_PATH + "load_binary_file")
    def test_all_utf8_encoded(self, m_load_file):
        """common path where only utf-8 decodable content."""
        content = self.null.join((self.simple1, self.simple2))
        m_load_file.return_value = content
        self.assertEqual(
            {"HOME": "/", "PATH": "/bin:/sbin"}, util.get_proc_env(1)
        )
        self.assertEqual(1, m_load_file.call_count)

    @mock.patch(M_PATH + "load_binary_file")
    def test_non_existing_file_returns_empty_dict(self, m_load_file):
        """as implemented, a non-existing pid returns empty dict.
        This is how it was originally implemented."""
        m_load_file.side_effect = OSError("File does not exist.")
        self.assertEqual({}, util.get_proc_env(1))
        self.assertEqual(1, m_load_file.call_count)


class TestGetProcPpid(helpers.TestCase):
    """test get_proc_ppid"""

    @skipIf(not util.is_Linux(), "/proc/$pid/stat is not useful on not-Linux")
    def test_get_proc_ppid_linux(self):
        """get_proc_ppid returns correct parent pid value."""
        my_pid = os.getpid()
        my_ppid = os.getppid()
        self.assertEqual(my_ppid, Distro.get_proc_ppid(my_pid))

    @skipIf(not util.is_Linux(), "/proc/$pid/stat is not useful on not-Linux")
    def test_get_proc_pgrp_linux(self):
        """get_proc_ppid returns correct parent pid value."""
        self.assertEqual(os.getpgid(0), Distro.get_proc_pgid(os.getpid()))

    @pytest.mark.allow_subp_for("ps")
    def test_get_proc_ppid_ps(self):
        """get_proc_ppid returns correct parent pid value."""
        my_pid = os.getpid()
        my_ppid = os.getppid()
        self.assertEqual(my_ppid, Distro.get_proc_ppid(my_pid))

    def test_get_proc_ppid_mocked(self):
        for ppid, proc_data in (
            (
                0,
                "1 (systemd) S 0 1 1 0 -1 4194560 112664 14612195 153 18014"
                "274 237 756828 152754 20 0 1 0 3 173809664 3736"
                "18446744073709551615 1 1 0 0 0 0 671173123 4096 1260 0 0 0 17"
                "8 0 0 0 0 123974 0 0 0 0 0 0 0 0",
            ),
            (
                180771,
                "180781 ([pytest-xdist r) R 180771 180598 167240 34825 "
                "180598 4194304 128712 7570 0 0 1061 34 8 1 20 0 2 0 6551540 "
                "351993856 25173 18446744073709551615 93907896635392 "
                "93907899455533 140725724279536 0 0 0 0 16781312 17642 0 0 0 "
                "17 1 0 0 0 0 0 93907901810800 93907902095288 93907928788992 "
                "140725724288007 140725724288074 140725724288074 "
                "140725724291047 0",
            ),
            (
                5620,
                "8723 (Utility Process) S 5620 5191 5191 0 -1 4194304 3219 "
                "0 50 0 1045 431 0 0 20 0 3 0 9007 220585984 8758 "
                "18446744073709551615 94469734690816 94469735319392 "
                "140728350183632 0 0 0 0 69634 1073745144 0 0 0 17 10 0 0 0 0 "
                "0 94469735327152 94469735331056 94469763170304 "
                "140728350189012 140728350189221 140728350189221 "
                "140728350195661 0",
            ),
            (
                4946,
                "4947 ((sd-pam)) S 4946 4946 4946 0 -1 1077936448 54 0 0 0 "
                "0 0 0 0 20 0 1 0 4136 175616000 1394 18446744073709551615 1 1"
                "0 0 0 0 0 4096 0 0 0 0 17 8 0 0 0 0 0 0 0 0 0 0 0 0 0",
            ),
            (
                144855,
                "167644 (python) R 144855 167644 144855 34819 167644 4194304 "
                "12692 0 0 0 114 10 0 0 20 0 1 0 8929754 69824512 13959 "
                "18446744073709551615 4321280 7154413 140733469268592 0 0 0 0 "
                "16781312 1258 0 0 0 17 0 0 0 0 0 0 9719240 11022936 13484032 "
                "140733469277329 140733469277436 140733469277436 "
                "140733469282250 0",
            ),
        ):
            with mock.patch(
                "cloudinit.util.load_text_file", return_value=proc_data
            ):
                assert ppid == Distro.get_proc_ppid(-999)


class TestHuman2Bytes:
    """test util.human2bytes() function"""

    def test_human2bytes(self):
        assert util.human2bytes("0.5G") == 536870912
        assert util.human2bytes("100B") == 100
        assert util.human2bytes("100MB") == 104857600

        for test_i in ["-100MB", "100b", "100mB"]:
            with pytest.raises(ValueError):
                util.human2bytes(test_i)

    def test_ibibytes2bytes(self):
        assert util.human2bytes("0.5GiB") == 536870912
        assert util.human2bytes("100MiB") == 104857600


class TestKernelVersion:
    """test kernel version function"""

    params = [
        ("5.6.19-300.fc32.x86_64", (5, 6)),
        ("4.15.0-101-generic", (4, 15)),
        ("3.10.0-1062.12.1.vz7.131.10", (3, 10)),
        ("4.18.0-144.el8.x86_64", (4, 18)),
    ]

    @mock.patch("os.uname")
    @pytest.mark.parametrize("uname_release,expected", params)
    def test_kernel_version(self, m_uname, uname_release, expected):
        m_uname.return_value.release = uname_release
        assert expected == util.kernel_version()


class TestFindDevs:
    @mock.patch("cloudinit.subp.subp")
    def test_find_devs_with(self, m_subp):
        m_subp.return_value = (
            '/dev/sda1: UUID="some-uuid" TYPE="ext4" PARTUUID="some-partid"',
            "",
        )
        devlist = util.find_devs_with()
        assert devlist == [
            '/dev/sda1: UUID="some-uuid" TYPE="ext4" PARTUUID="some-partid"'
        ]

        devlist = util.find_devs_with("LABEL_FATBOOT=A_LABEL")
        assert devlist == [
            '/dev/sda1: UUID="some-uuid" TYPE="ext4" PARTUUID="some-partid"'
        ]

    @mock.patch("cloudinit.subp.subp")
    def test_find_devs_with_openbsd(self, m_subp):
        m_subp.return_value = SubpResult(
            "cd0:,sd0:630d98d32b5d3759,sd1:,fd0:", ""
        )
        devlist = util.find_devs_with_openbsd()
        assert devlist == ["/dev/cd0a", "/dev/sd1a", "/dev/sd1i"]

    @mock.patch("cloudinit.subp.subp")
    def test_find_devs_with_openbsd_with_criteria(self, m_subp):
        m_subp.return_value = SubpResult(
            "cd0:,sd0:630d98d32b5d3759,sd1:,fd0:", ""
        )
        devlist = util.find_devs_with_openbsd(criteria="TYPE=iso9660")
        assert devlist == ["/dev/cd0a", "/dev/sd1a", "/dev/sd1i"]

        # lp: #1841466
        devlist = util.find_devs_with_openbsd(criteria="LABEL_FATBOOT=A_LABEL")
        assert devlist == ["/dev/cd0a", "/dev/sd1a", "/dev/sd1i"]

    @pytest.mark.parametrize(
        "criteria,expected_devlist",
        (
            (None, ["/dev/msdosfs/EFISYS", "/dev/iso9660/config-2"]),
            ("TYPE=iso9660", ["/dev/iso9660/config-2"]),
            ("TYPE=vfat", ["/dev/msdosfs/EFISYS"]),
            ("LABEL_FATBOOT=A_LABEL", []),  # lp: #1841466
        ),
    )
    @mock.patch("glob.glob")
    def test_find_devs_with_freebsd(self, m_glob, criteria, expected_devlist):
        def fake_glob(pattern):
            msdos = ["/dev/msdosfs/EFISYS"]
            iso9660 = ["/dev/iso9660/config-2"]
            if pattern == "/dev/msdosfs/*":
                return msdos
            elif pattern == "/dev/iso9660/*":
                return iso9660
            raise RuntimeError

        m_glob.side_effect = fake_glob

        devlist = util.find_devs_with_freebsd(criteria=criteria)
        assert devlist == expected_devlist

    @pytest.mark.parametrize(
        "criteria,expected_devlist",
        (
            (None, ["/dev/ld0", "/dev/dk0", "/dev/dk1", "/dev/cd0"]),
            ("TYPE=iso9660", ["/dev/cd0"]),
            ("TYPE=vfat", ["/dev/ld0", "/dev/dk0", "/dev/dk1"]),
            (
                "LABEL_FATBOOT=A_LABEL",  # lp: #1841466
                ["/dev/ld0", "/dev/dk0", "/dev/dk1", "/dev/cd0"],
            ),
        ),
    )
    @mock.patch("cloudinit.subp.subp")
    def test_find_devs_with_netbsd(self, m_subp, criteria, expected_devlist):
        side_effect_values = [
            SubpResult("ld0 dk0 dk1 cd0", ""),
            SubpResult(
                "mscdlabel: CDIOREADTOCHEADER: "
                "Inappropriate ioctl for device\n"
                "track (ctl=4) at sector 0\n"
                "disklabel not written\n",
                "",
            ),
            SubpResult(
                "mscdlabel: CDIOREADTOCHEADER: "
                "Inappropriate ioctl for device\n"
                "track (ctl=4) at sector 0\n"
                "disklabel not written\n",
                "",
            ),
            SubpResult(
                "mscdlabel: CDIOREADTOCHEADER: "
                "Inappropriate ioctl for device\n"
                "track (ctl=4) at sector 0\n"
                "disklabel not written\n",
                "",
            ),
            SubpResult(
                "track (ctl=4) at sector 0\n"
                'ISO filesystem, label "config-2", '
                "creation time: 2020/03/31 17:29\n"
                "adding as 'a'\n",
                "",
            ),
        ]
        m_subp.side_effect = side_effect_values
        devlist = util.find_devs_with_netbsd(criteria=criteria)
        assert devlist == expected_devlist

    @pytest.mark.parametrize(
        "criteria,expected_devlist",
        (
            (None, ["/dev/vbd0", "/dev/cd0", "/dev/acd0"]),
            ("TYPE=iso9660", ["/dev/cd0", "/dev/acd0"]),
            ("TYPE=vfat", ["/dev/vbd0"]),
            (
                "LABEL_FATBOOT=A_LABEL",  # lp: #1841466
                ["/dev/vbd0", "/dev/cd0", "/dev/acd0"],
            ),
        ),
    )
    @mock.patch("cloudinit.subp.subp")
    def test_find_devs_with_dragonflybsd(
        self, m_subp, criteria, expected_devlist
    ):
        m_subp.return_value = SubpResult(
            "md2 md1 cd0 vbd0 acd0 vn3 vn2 vn1 vn0 md0", ""
        )
        devlist = util.find_devs_with_dragonflybsd(criteria=criteria)
        assert devlist == expected_devlist


class TestVersion:
    @pytest.mark.parametrize(
        ("v1", "v2", "eq"),
        (
            ("3.1.0", "3.1.0", True),
            ("3.1.0", "3.1.1", False),
            ("3.1", "3.1.0.0", False),
        ),
    )
    def test_eq(self, v1, v2, eq):
        if eq:
            assert util.Version.from_str(v1) == util.Version.from_str(v2)
        if not eq:
            assert util.Version.from_str(v1) != util.Version.from_str(v2)

    @pytest.mark.parametrize(
        ("v1", "v2", "gt"),
        (
            ("3.1.0", "3.1.0", False),
            ("3.1.0", "3.1.1", False),
            ("3.1", "3.1.0.0", False),
            ("3.1.0.0", "3.1", True),
            ("3.1.1", "3.1.0", True),
        ),
    )
    def test_gt(self, v1, v2, gt):
        if gt:
            assert util.Version.from_str(v1) > util.Version.from_str(v2)
        if not gt:
            assert util.Version.from_str(v1) < util.Version.from_str(
                v2
            ) or util.Version.from_str(v1) == util.Version.from_str(v2)

    @pytest.mark.parametrize(
        ("version"),
        (
            ("3.1.0"),
            ("3.0.1"),
            ("3.1"),
            ("3.1.0.0"),
            ("3.1.1"),
        ),
    )
    def test_to_version_and_back_to_str(self, version):
        """Verify __str__, __iter__, and Version.from_str()"""
        assert version == str(util.Version.from_str(version))

    @pytest.mark.parametrize(
        ("str_ver", "cls_ver"),
        (
            (
                "0.0.0.0",
                util.Version(0, 0, 0, 0),
            ),
            (
                "1.0.0.0",
                util.Version(1, 0, 0, 0),
            ),
            (
                "1.0.2.0",
                util.Version(1, 0, 2, 0),
            ),
            (
                "9.8.2.0",
                util.Version(9, 8, 2, 0),
            ),
        ),
    )
    def test_from_str(self, str_ver, cls_ver):
        assert util.Version.from_str(str_ver) == cls_ver


@pytest.mark.allow_dns_lookup
class TestResolvable:
    @mock.patch.object(util, "_DNS_REDIRECT_IP", return_value=True)
    @mock.patch.object(util.socket, "getaddrinfo")
    def test_ips_need_not_be_resolved(self, m_getaddr, m_dns):
        """Optimization test: dns resolution may timeout during early boot, and
        often the urls being checked use IP addresses rather than dns names.
        Therefore, the fast path checks if the address contains an IP and exits
        early if the path is a valid IP.
        """
        assert util.is_resolvable("http://169.254.169.254/") is True
        assert util.is_resolvable("http://[fd00:ec2::254]/") is True
        assert not m_getaddr.called


class TestHashBuffer:
    def test_in_memory(self):
        buf = io.BytesIO(b"hola")
        assert (
            util.hash_buffer(buf)
            == b"\x99\x80\x0b\x85\xd38>:/\xb4^\xb7\xd0\x06jHy\xa9\xda\xd0"
        )

    def test_file(self, tmp_path):
        content = b"hola"
        file = tmp_path / "file.txt"
        with file.open("wb") as f:
            f.write(content)

        with file.open("rb") as f:
            assert (
                util.hash_buffer(f)
                == b"\x99\x80\x0b\x85\xd38>:/\xb4^\xb7\xd0\x06jHy\xa9\xda\xd0"
            )


class TestMaybeB64Decode:
    """Test the maybe_b64decode helper function."""

    @pytest.mark.parametrize("invalid_input", (str("not bytes"), int(4)))
    def test_raises_error_on_non_bytes(self, invalid_input):
        """maybe_b64decode should raise error if data is not bytes."""
        with pytest.raises(TypeError):
            util.maybe_b64decode(invalid_input)

    @pytest.mark.parametrize(
        "in_data,expected",
        [
            # If data is not b64 encoded, then return value should be the same.
            (b"this is my data", b"this is my data"),
            # If data is b64 encoded, then return value should be decoded.
            (base64.b64encode(b"data"), b"data"),
        ],
    )
    def test_happy_path(self, in_data, expected):
        assert expected == util.maybe_b64decode(in_data)


class MockPath:
    def __init__(self, target_file="/does/not/exist"):
        self.target_file = target_file

    def get_cpath(self, *args):
        assert args == (
            "hotplug.enabled",
        ), f"Invalid get_cpath argument {args}"
        return self.target_file


@pytest.mark.usefixtures("fake_filesystem")
class TestReadHotplugEnabledFile:
    def test_file_not_found(self, caplog):
        assert {"scopes": []} == util.read_hotplug_enabled_file(MockPath())
        assert "enabled because it is not decodable" not in caplog.text

    def test_json_decode_error(self, caplog, tmpdir):
        target_file = (
            tmpdir.mkdir("var")
            .mkdir("lib")
            .mkdir("cloud")
            .join("hotplug.enabled")
        )
        target_file.write("asdfasdfa")
        assert {"scopes": []} == util.read_hotplug_enabled_file(
            MockPath(target_file.strpath)
        )
        assert "not decodable" in caplog.text

    @pytest.mark.parametrize("content", ['{"scopes": ["network"]}'])
    def test_file_present(self, content, caplog, tmpdir):
        target_file = (
            tmpdir.mkdir("var")
            .mkdir("lib")
            .mkdir("cloud")
            .join("hotplug.enabled")
        )
        target_file.write(content)
        assert {"scopes": ["network"]} == util.read_hotplug_enabled_file(
            MockPath(target_file.strpath)
        )


class TestLogExc:
    def test_logexc(self, caplog):
        try:
            _ = 1 / 0
        except Exception as _:
            util.logexc(LOG, "an error occurred")

        assert caplog.record_tuples == [
            (
                "tests.unittests.test_util",
                logging.WARNING,
                "an error occurred",
            ),
            ("tests.unittests.test_util", logging.DEBUG, "an error occurred"),
        ]

    @pytest.mark.parametrize(
        "log_level",
        [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR],
    )
    def test_logexc_with_log_level(self, caplog, log_level):
        try:
            _ = 1 / 0
        except Exception as _:
            util.logexc(LOG, "an error occurred", log_level=log_level)

        assert caplog.record_tuples == [
            (
                "tests.unittests.test_util",
                log_level,
                "an error occurred",
            ),
            ("tests.unittests.test_util", logging.DEBUG, "an error occurred"),
        ]
