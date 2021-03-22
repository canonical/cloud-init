# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.util"""

import base64
import logging
import json
import platform
import pytest

import cloudinit.util as util
from cloudinit import subp

from cloudinit.tests.helpers import CiTestCase, mock
from textwrap import dedent

LOG = logging.getLogger(__name__)

MOUNT_INFO = [
    '68 0 8:3 / / ro,relatime shared:1 - btrfs /dev/sda1 ro,attr2,inode64',
    '153 68 254:0 / /home rw,relatime shared:101 - xfs /dev/sda2 rw,attr2'
]

OS_RELEASE_SLES = dedent("""\
    NAME="SLES"
    VERSION="12-SP3"
    VERSION_ID="12.3"
    PRETTY_NAME="SUSE Linux Enterprise Server 12 SP3"
    ID="sles"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:suse:sles:12:sp3"
""")

OS_RELEASE_OPENSUSE = dedent("""\
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
""")

OS_RELEASE_OPENSUSE_L15 = dedent("""\
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
""")

OS_RELEASE_OPENSUSE_TW = dedent("""\
    NAME="openSUSE Tumbleweed"
    ID="opensuse-tumbleweed"
    ID_LIKE="opensuse suse"
    VERSION_ID="20180920"
    PRETTY_NAME="openSUSE Tumbleweed"
    ANSI_COLOR="0;32"
    CPE_NAME="cpe:/o:opensuse:tumbleweed:20180920"
    BUG_REPORT_URL="https://bugs.opensuse.org"
    HOME_URL="https://www.opensuse.org/"
""")

OS_RELEASE_CENTOS = dedent("""\
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
""")

OS_RELEASE_REDHAT_7 = dedent("""\
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
""")

REDHAT_RELEASE_CENTOS_6 = "CentOS release 6.10 (Final)"
REDHAT_RELEASE_CENTOS_7 = "CentOS Linux release 7.5.1804 (Core)"
REDHAT_RELEASE_REDHAT_6 = (
    "Red Hat Enterprise Linux Server release 6.10 (Santiago)")
REDHAT_RELEASE_REDHAT_7 = (
    "Red Hat Enterprise Linux Server release 7.5 (Maipo)")


OS_RELEASE_DEBIAN = dedent("""\
    PRETTY_NAME="Debian GNU/Linux 9 (stretch)"
    NAME="Debian GNU/Linux"
    VERSION_ID="9"
    VERSION="9 (stretch)"
    ID=debian
    HOME_URL="https://www.debian.org/"
    SUPPORT_URL="https://www.debian.org/support"
    BUG_REPORT_URL="https://bugs.debian.org/"
""")

OS_RELEASE_UBUNTU = dedent("""\
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
""")


class FakeCloud(object):

    def __init__(self, hostname, fqdn):
        self.hostname = hostname
        self.fqdn = fqdn
        self.calls = []

    def get_hostname(self, fqdn=None, metadata_only=None):
        myargs = {}
        if fqdn is not None:
            myargs['fqdn'] = fqdn
        if metadata_only is not None:
            myargs['metadata_only'] = metadata_only
        self.calls.append(myargs)
        if fqdn:
            return self.fqdn
        return self.hostname


class TestUtil(CiTestCase):

    def test_parse_mount_info_no_opts_no_arg(self):
        result = util.parse_mount_info('/home', MOUNT_INFO, LOG)
        self.assertEqual(('/dev/sda2', 'xfs', '/home'), result)

    def test_parse_mount_info_no_opts_arg(self):
        result = util.parse_mount_info('/home', MOUNT_INFO, LOG, False)
        self.assertEqual(('/dev/sda2', 'xfs', '/home'), result)

    def test_parse_mount_info_with_opts(self):
        result = util.parse_mount_info('/', MOUNT_INFO, LOG, True)
        self.assertEqual(
            ('/dev/sda1', 'btrfs', '/', 'ro,relatime'),
            result
        )

    @mock.patch('cloudinit.util.get_mount_info')
    def test_mount_is_rw(self, m_mount_info):
        m_mount_info.return_value = ('/dev/sda1', 'btrfs', '/', 'rw,relatime')
        is_rw = util.mount_is_read_write('/')
        self.assertEqual(is_rw, True)

    @mock.patch('cloudinit.util.get_mount_info')
    def test_mount_is_ro(self, m_mount_info):
        m_mount_info.return_value = ('/dev/sda1', 'btrfs', '/', 'ro,relatime')
        is_rw = util.mount_is_read_write('/')
        self.assertEqual(is_rw, False)


class TestUptime(CiTestCase):

    @mock.patch('cloudinit.util.boottime')
    @mock.patch('cloudinit.util.os.path.exists')
    @mock.patch('cloudinit.util.time.time')
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
            TypeError, 'Input.*was.*dict.*xpected',
            util.shellify, {'mykey': 'myval'})

    def test_input_str_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, 'Input.*was.*str.*xpected', util.shellify, "foobar")

    def test_value_with_int_raises_type_error(self):
        self.assertRaisesRegex(
            TypeError, 'shellify.*int', util.shellify, ["foo", 1])

    def test_supports_strings_and_lists(self):
        self.assertEqual(
            '\n'.join(["#!/bin/sh", "echo hi mom", "'echo' 'hi dad'",
                       "'echo' 'hi' 'sis'", ""]),
            util.shellify(["echo hi mom", ["echo", "hi dad"],
                           ('echo', 'hi', 'sis')]))


class TestGetHostnameFqdn(CiTestCase):

    def test_get_hostname_fqdn_from_only_cfg_fqdn(self):
        """When cfg only has the fqdn key, derive hostname and fqdn from it."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'fqdn': 'myhost.domain.com'}, cloud=None)
        self.assertEqual('myhost', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_fqdn_and_hostname(self):
        """When cfg has both fqdn and hostname keys, return them."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'fqdn': 'myhost.domain.com', 'hostname': 'other'}, cloud=None)
        self.assertEqual('other', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_with_domain(self):
        """When cfg has only hostname key which represents a fqdn, use that."""
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'hostname': 'myhost.domain.com'}, cloud=None)
        self.assertEqual('myhost', hostname)
        self.assertEqual('myhost.domain.com', fqdn)

    def test_get_hostname_fqdn_from_cfg_hostname_without_domain(self):
        """When cfg has a hostname without a '.' query cloud.get_hostname."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        hostname, fqdn = util.get_hostname_fqdn(
            cfg={'hostname': 'myhost'}, cloud=mycloud)
        self.assertEqual('myhost', hostname)
        self.assertEqual('cloudhost.mycloud.com', fqdn)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': False}], mycloud.calls)

    def test_get_hostname_fqdn_from_without_fqdn_or_hostname(self):
        """When cfg has neither hostname nor fqdn cloud.get_hostname."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        hostname, fqdn = util.get_hostname_fqdn(cfg={}, cloud=mycloud)
        self.assertEqual('cloudhost', hostname)
        self.assertEqual('cloudhost.mycloud.com', fqdn)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': False},
             {'metadata_only': False}], mycloud.calls)

    def test_get_hostname_fqdn_from_passes_metadata_only_to_cloud(self):
        """Calls to cloud.get_hostname pass the metadata_only parameter."""
        mycloud = FakeCloud('cloudhost', 'cloudhost.mycloud.com')
        _hn, _fqdn = util.get_hostname_fqdn(
            cfg={}, cloud=mycloud, metadata_only=True)
        self.assertEqual(
            [{'fqdn': True, 'metadata_only': True},
             {'metadata_only': True}], mycloud.calls)


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

    blkid_out = dedent("""\
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
      """)

    maxDiff = None

    def _get_expected(self):
        return ({
            "/dev/loop0": {"DEVNAME": "/dev/loop0", "TYPE": "squashfs"},
            "/dev/loop1": {"DEVNAME": "/dev/loop1", "TYPE": "squashfs"},
            "/dev/loop2": {"DEVNAME": "/dev/loop2", "TYPE": "squashfs"},
            "/dev/loop3": {"DEVNAME": "/dev/loop3", "TYPE": "squashfs"},
            "/dev/loop4": {"DEVNAME": "/dev/loop4", "TYPE": "squashfs"},
            "/dev/sda1": {"DEVNAME": "/dev/sda1", "TYPE": "vfat",
                          "UUID": self.ids["id01"],
                          "PARTUUID": self.ids["id02"]},
            "/dev/sda2": {"DEVNAME": "/dev/sda2", "TYPE": "ext4",
                          "UUID": self.ids["id03"],
                          "PARTUUID": self.ids["id04"]},
            "/dev/sda3": {"DEVNAME": "/dev/sda3", "TYPE": "ext4",
                          "UUID": self.ids["id05"],
                          "PARTUUID": self.ids["id06"]},
            "/dev/sda4": {"DEVNAME": "/dev/sda4", "TYPE": "zfs_member",
                          "LABEL": "default",
                          "UUID": self.ids["id07"],
                          "UUID_SUB": self.ids["id08"],
                          "PARTUUID": self.ids["id09"]},
        })

    @mock.patch("cloudinit.subp.subp")
    def test_functional_blkid(self, m_subp):
        m_subp.return_value = (
            self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(), util.blkid())
        m_subp.assert_called_with(["blkid", "-o", "full"], capture=True,
                                  decode="replace")

    @mock.patch("cloudinit.subp.subp")
    def test_blkid_no_cache_uses_no_cache(self, m_subp):
        """blkid should turn off cache if disable_cache is true."""
        m_subp.return_value = (
            self.blkid_out.format(**self.ids), "")
        self.assertEqual(self._get_expected(),
                         util.blkid(disable_cache=True))
        m_subp.assert_called_with(["blkid", "-o", "full", "-c", "/dev/null"],
                                  capture=True, decode="replace")


@mock.patch('cloudinit.subp.subp')
class TestUdevadmSettle(CiTestCase):
    def test_with_no_params(self, m_subp):
        """called with no parameters."""
        util.udevadm_settle()
        m_subp.called_once_with(mock.call(['udevadm', 'settle']))

    def test_with_exists_and_not_exists(self, m_subp):
        """with exists=file where file does not exist should invoke subp."""
        mydev = self.tmp_path("mydev")
        util.udevadm_settle(exists=mydev)
        m_subp.called_once_with(
            ['udevadm', 'settle', '--exit-if-exists=%s' % mydev])

    def test_with_exists_and_file_exists(self, m_subp):
        """with exists=file where file does exist should not invoke subp."""
        mydev = self.tmp_path("mydev")
        util.write_file(mydev, "foo\n")
        util.udevadm_settle(exists=mydev)
        self.assertIsNone(m_subp.call_args)

    def test_with_timeout_int(self, m_subp):
        """timeout can be an integer."""
        timeout = 9
        util.udevadm_settle(timeout=timeout)
        m_subp.called_once_with(
            ['udevadm', 'settle', '--timeout=%s' % timeout])

    def test_with_timeout_string(self, m_subp):
        """timeout can be a string."""
        timeout = "555"
        util.udevadm_settle(timeout=timeout)
        m_subp.assert_called_once_with(
            ['udevadm', 'settle', '--timeout=%s' % timeout])

    def test_with_exists_and_timeout(self, m_subp):
        """test call with both exists and timeout."""
        mydev = self.tmp_path("mydev")
        timeout = "3"
        util.udevadm_settle(exists=mydev)
        m_subp.called_once_with(
            ['udevadm', 'settle', '--exit-if-exists=%s' % mydev,
             '--timeout=%s' % timeout])

    def test_subp_exception_raises_to_caller(self, m_subp):
        m_subp.side_effect = subp.ProcessExecutionError("BOOM")
        self.assertRaises(subp.ProcessExecutionError, util.udevadm_settle)


@mock.patch('os.path.exists')
class TestGetLinuxDistro(CiTestCase):

    def setUp(self):
        # python2 has no lru_cache, and therefore, no cache_clear()
        if hasattr(util.get_linux_distro, "cache_clear"):
            util.get_linux_distro.cache_clear()

    @classmethod
    def os_release_exists(self, path):
        """Side effect function"""
        if path == '/etc/os-release':
            return 1

    @classmethod
    def redhat_release_exists(self, path):
        """Side effect function """
        if path == '/etc/redhat-release':
            return 1

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_distro_quoted_name(self, m_os_release, m_path_exists):
        """Verify we get the correct name if the os-release file has
        the distro name in quotes"""
        m_os_release.return_value = OS_RELEASE_SLES
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('sles', '12.3', platform.machine()), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_distro_bare_name(self, m_os_release, m_path_exists):
        """Verify we get the correct name if the os-release file does not
        have the distro name in quotes"""
        m_os_release.return_value = OS_RELEASE_UBUNTU
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('ubuntu', '16.04', 'xenial'), dist)

    @mock.patch('platform.system')
    @mock.patch('platform.release')
    @mock.patch('cloudinit.util._parse_redhat_release')
    def test_get_linux_freebsd(self, m_parse_redhat_release,
                               m_platform_release,
                               m_platform_system, m_path_exists):
        """Verify we get the correct name and release name on FreeBSD."""
        m_path_exists.return_value = False
        m_platform_release.return_value = '12.0-RELEASE-p10'
        m_platform_system.return_value = 'FreeBSD'
        m_parse_redhat_release.return_value = {}
        util.is_BSD.cache_clear()
        dist = util.get_linux_distro()
        self.assertEqual(('freebsd', '12.0-RELEASE-p10', ''), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_centos6(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on CentOS 6."""
        m_os_release.return_value = REDHAT_RELEASE_CENTOS_6
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('centos', '6.10', 'Final'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_centos7_redhat_release(self, m_os_release, m_exists):
        """Verify the correct release info on CentOS 7 without os-release."""
        m_os_release.return_value = REDHAT_RELEASE_CENTOS_7
        m_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('centos', '7.5.1804', 'Core'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_redhat7_osrelease(self, m_os_release, m_path_exists):
        """Verify redhat 7 read from os-release."""
        m_os_release.return_value = OS_RELEASE_REDHAT_7
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('redhat', '7.5', 'Maipo'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_redhat7_rhrelease(self, m_os_release, m_path_exists):
        """Verify redhat 7 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_REDHAT_7
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('redhat', '7.5', 'Maipo'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_redhat6_rhrelease(self, m_os_release, m_path_exists):
        """Verify redhat 6 read from redhat-release."""
        m_os_release.return_value = REDHAT_RELEASE_REDHAT_6
        m_path_exists.side_effect = TestGetLinuxDistro.redhat_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('redhat', '6.10', 'Santiago'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_copr_centos(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on COPR CentOS."""
        m_os_release.return_value = OS_RELEASE_CENTOS
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('centos', '7', 'Core'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_debian(self, m_os_release, m_path_exists):
        """Verify we get the correct name and release name on Debian."""
        m_os_release.return_value = OS_RELEASE_DEBIAN
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('debian', '9', 'stretch'), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_opensuse(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
           prior to openSUSE Leap 15.
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('opensuse', '42.3', platform.machine()), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_opensuse_l15(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
           for openSUSE Leap 15.0 and later.
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE_L15
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(('opensuse-leap', '15.0', platform.machine()), dist)

    @mock.patch('cloudinit.util.load_file')
    def test_get_linux_opensuse_tw(self, m_os_release, m_path_exists):
        """Verify we get the correct name and machine arch on openSUSE
           for openSUSE Tumbleweed
        """
        m_os_release.return_value = OS_RELEASE_OPENSUSE_TW
        m_path_exists.side_effect = TestGetLinuxDistro.os_release_exists
        dist = util.get_linux_distro()
        self.assertEqual(
            ('opensuse-tumbleweed', '20180920', platform.machine()), dist)

    @mock.patch('platform.system')
    @mock.patch('platform.dist', create=True)
    def test_get_linux_distro_no_data(self, m_platform_dist,
                                      m_platform_system, m_path_exists):
        """Verify we get no information if os-release does not exist"""
        m_platform_dist.return_value = ('', '', '')
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(('', '', ''), dist)

    @mock.patch('platform.system')
    @mock.patch('platform.dist', create=True)
    def test_get_linux_distro_no_impl(self, m_platform_dist,
                                      m_platform_system, m_path_exists):
        """Verify we get an empty tuple when no information exists and
        Exceptions are not propagated"""
        m_platform_dist.side_effect = Exception()
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(('', '', ''), dist)

    @mock.patch('platform.system')
    @mock.patch('platform.dist', create=True)
    def test_get_linux_distro_plat_data(self, m_platform_dist,
                                        m_platform_system, m_path_exists):
        """Verify we get the correct platform information"""
        m_platform_dist.return_value = ('foo', '1.1', 'aarch64')
        m_platform_system.return_value = "Linux"
        m_path_exists.return_value = 0
        dist = util.get_linux_distro()
        self.assertEqual(('foo', '1.1', 'aarch64'), dist)


class TestJsonDumps(CiTestCase):
    def test_is_str(self):
        """json_dumps should return a string."""
        self.assertTrue(isinstance(util.json_dumps({'abc': '123'}), str))

    def test_utf8(self):
        smiley = '\\ud83d\\ude03'
        self.assertEqual(
            {'smiley': smiley},
            json.loads(util.json_dumps({'smiley': smiley})))

    def test_non_utf8(self):
        blob = b'\xba\x03Qx-#y\xea'
        self.assertEqual(
            {'blob': 'ci-b64:' + base64.b64encode(blob).decode('utf-8')},
            json.loads(util.json_dumps({'blob': blob})))


@mock.patch('os.path.exists')
class TestIsLXD(CiTestCase):

    def test_is_lxd_true_on_sock_device(self, m_exists):
        """When lxd's /dev/lxd/sock exists, is_lxd returns true."""
        m_exists.return_value = True
        self.assertTrue(util.is_lxd())
        m_exists.assert_called_once_with('/dev/lxd/sock')

    def test_is_lxd_false_when_sock_device_absent(self, m_exists):
        """When lxd's /dev/lxd/sock is absent, is_lxd returns false."""
        m_exists.return_value = False
        self.assertFalse(util.is_lxd())
        m_exists.assert_called_once_with('/dev/lxd/sock')


class TestReadCcFromCmdline:

    @pytest.mark.parametrize(
        "cmdline,expected_cfg",
        [
            # Return None if cmdline has no cc:<YAML>end_cc content.
            (CiTestCase.random_string(), None),
            # Return None if YAML content is empty string.
            ('foo cc: end_cc bar', None),
            # Return expected dictionary without trailing end_cc marker.
            ('foo cc: ssh_pwauth: true', {'ssh_pwauth': True}),
            # Return expected dictionary w escaped newline and no end_cc.
            ('foo cc: ssh_pwauth: true\\n', {'ssh_pwauth': True}),
            # Return expected dictionary of yaml between cc: and end_cc.
            ('foo cc: ssh_pwauth: true end_cc bar', {'ssh_pwauth': True}),
            # Return dict with list value w escaped newline, no end_cc.
            (
                'cc: ssh_import_id: [smoser, kirkland]\\n',
                {'ssh_import_id': ['smoser', 'kirkland']}
            ),
            # Parse urlencoded brackets in yaml content.
            (
                'cc: ssh_import_id: %5Bsmoser, kirkland%5D end_cc',
                {'ssh_import_id': ['smoser', 'kirkland']}
            ),
            # Parse complete urlencoded yaml content.
            (
                'cc: ssh_import_id%3A%20%5Buser1%2C%20user2%5D end_cc',
                {'ssh_import_id': ['user1', 'user2']}
            ),
            # Parse nested dictionary in yaml content.
            (
                'cc: ntp: {enabled: true, ntp_client: myclient} end_cc',
                {'ntp': {'enabled': True, 'ntp_client': 'myclient'}}
            ),
            # Parse single mapping value in yaml content.
            ('cc: ssh_import_id: smoser end_cc', {'ssh_import_id': 'smoser'}),
            # Parse multiline content with multiple mapping and nested lists.
            (
                ('cc: ssh_import_id: [smoser, bob]\\n'
                 'runcmd: [ [ ls, -l ], echo hi ] end_cc'),
                {'ssh_import_id': ['smoser', 'bob'],
                 'runcmd': [['ls', '-l'], 'echo hi']}
            ),
            # Parse multiline encoded content w/ mappings and nested lists.
            (
                ('cc: ssh_import_id: %5Bsmoser, bob%5D\\n'
                 'runcmd: [ [ ls, -l ], echo hi ] end_cc'),
                {'ssh_import_id': ['smoser', 'bob'],
                 'runcmd': [['ls', '-l'], 'echo hi']}
            ),
            # test encoded escaped newlines work.
            #
            # unquote(encoded_content)
            # 'ssh_import_id: [smoser, bob]\\nruncmd: [ [ ls, -l ], echo hi ]'
            (
                ('cc: ' +
                 ('ssh_import_id%3A%20%5Bsmoser%2C%20bob%5D%5Cn'
                  'runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%2C'
                  '%20echo%20hi%20%5D') + ' end_cc'),
                {'ssh_import_id': ['smoser', 'bob'],
                 'runcmd': [['ls', '-l'], 'echo hi']}
            ),
            # test encoded newlines work.
            #
            # unquote(encoded_content)
            # 'ssh_import_id: [smoser, bob]\nruncmd: [ [ ls, -l ], echo hi ]'
            (
                ("cc: " +
                    ('ssh_import_id%3A%20%5Bsmoser%2C%20bob%5D%0A'
                     'runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%2C'
                     '%20echo%20hi%20%5D') + ' end_cc'),
                {'ssh_import_id': ['smoser', 'bob'],
                 'runcmd': [['ls', '-l'], 'echo hi']}
            ),
            # Parse and merge multiple yaml content sections.
            (
                ('cc:ssh_import_id: [smoser, bob] end_cc '
                 'cc: runcmd: [ [ ls, -l ] ] end_cc'),
                {'ssh_import_id': ['smoser', 'bob'],
                 'runcmd': [['ls', '-l']]}
            ),
            # Parse and merge multiple encoded yaml content sections.
            (
                ('cc:ssh_import_id%3A%20%5Bsmoser%5D end_cc '
                 'cc:runcmd%3A%20%5B%20%5B%20ls%2C%20-l%20%5D%20%5D end_cc'),
                {'ssh_import_id': ['smoser'], 'runcmd': [['ls', '-l']]}
            ),
        ]
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

    @pytest.yield_fixture
    def already_mounted_device_and_mountdict(self):
        """Mock an already-mounted device, and yield (device, mount dict)"""
        device = "/dev/fake0"
        mountpoint = "/mnt/fake"
        with mock.patch("cloudinit.util.subp.subp"):
            with mock.patch("cloudinit.util.mounts") as m_mounts:
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
            ("ufs", "ufs")
        ],
    )
    @mock.patch("cloudinit.util.is_Linux", autospec=True)
    @mock.patch("cloudinit.util.is_BSD", autospec=True)
    @mock.patch("cloudinit.util.subp.subp")
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

        util.mount_cb('/dev/fake0', callback, mtype=mtype)
        assert mock.call(
            ["mount", "-o", "ro", "-t", expected, "/dev/fake0", "/tmp/fake"],
            update_env=None) in m_subp.call_args_list

    @pytest.mark.parametrize("invalid_mtype", [int(0), float(0.0), dict()])
    def test_typeerror_raised_for_invalid_mtype(self, invalid_mtype):
        with pytest.raises(TypeError):
            util.mount_cb(mock.Mock(), mock.Mock(), mtype=invalid_mtype)

    @mock.patch("cloudinit.util.subp.subp")
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


@mock.patch("cloudinit.util.write_file")
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


@mock.patch("cloudinit.util.grp.getgrnam")
@mock.patch("cloudinit.util.os.setgid")
@mock.patch("cloudinit.util.os.umask")
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
        with mock.patch("cloudinit.util.subprocess.Popen") as m_popen:
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

# vi: ts=4 expandtab
