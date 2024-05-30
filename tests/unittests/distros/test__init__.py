# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil
import tempfile
from unittest import mock

import pytest

from cloudinit import distros, util
from cloudinit.distros.ubuntu import Distro
from cloudinit.net.dhcp import Dhcpcd, IscDhclient, Udhcpc
from tests.unittests import helpers

M_PATH = "cloudinit.distros."

unknown_arch_info = {
    "arches": ["default"],
    "failsafe": {
        "primary": "http://fs-primary-default",
        "security": "http://fs-security-default",
    },
}

package_mirrors = [
    {
        "arches": ["i386", "amd64"],
        "failsafe": {
            "primary": "http://fs-primary-intel",
            "security": "http://fs-security-intel",
        },
        "search": {
            "primary": [
                "http://%(ec2_region)s.ec2/",
                "http://%(availability_zone)s.clouds/",
            ],
            "security": [
                "http://security-mirror1-intel",
                "http://security-mirror2-intel",
            ],
        },
    },
    {
        "arches": ["armhf", "armel"],
        "failsafe": {
            "primary": "http://fs-primary-arm",
            "security": "http://fs-security-arm",
        },
    },
    unknown_arch_info,
]

gpmi = distros._get_package_mirror_info
gapmi = distros._get_arch_package_mirror_info


class TestGenericDistro(helpers.FilesystemMockingTestCase):
    with_logs = True

    def setUp(self):
        super(TestGenericDistro, self).setUp()
        # Make a temp directoy for tests to use.
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _write_load_doas(self, user, rules):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        if not os.path.exists(os.path.join(self.tmp, "etc")):
            os.makedirs(os.path.join(self.tmp, "etc"))
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        d.write_doas_rules(user, rules)
        contents = util.load_text_file(d.doas_fn)
        return contents, cls, d

    def _write_load_sudoers(self, _user, rules):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        os.makedirs(os.path.join(self.tmp, "etc"))
        os.makedirs(os.path.join(self.tmp, "etc", "sudoers.d"))
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        d.write_sudo_rules("harlowja", rules)
        contents = util.load_text_file(d.ci_sudoers_fn)
        return contents, cls, d

    def _count_in(self, lines_look_for, text_content):
        found_amount = 0
        for e in lines_look_for:
            for line in text_content.splitlines():
                line = line.strip()
                if line == e:
                    found_amount += 1
        return found_amount

    def test_doas_ensure_rules(self):
        rules = ["permit nopass harlowja"]
        contents = self._write_load_doas("harlowja", rules)[0]
        expected = ["permit nopass harlowja"]
        self.assertEqual(len(expected), self._count_in(expected, contents))

    def test_doas_ensure_rules_list(self):
        rules = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        contents = self._write_load_doas("harlowja", rules)[0]
        expected = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        self.assertEqual(len(expected), self._count_in(expected, contents))

    def test_doas_ensure_handle_duplicates(self):
        rules = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        d = self._write_load_doas("harlowja", rules)[2]
        # write to doas.conf again - should not create duplicate rules
        d.write_doas_rules("harlowja", rules)
        contents = util.load_text_file(d.doas_fn)
        expected = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        self.assertEqual(len(expected), self._count_in(expected, contents))

    def test_doas_ensure_new(self):
        rules = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        contents = self._write_load_doas("harlowja", rules)[0]
        self.assertIn("# Created by cloud-init v.", contents)
        self.assertIn("harlowja", contents)
        self.assertEqual(4, contents.count("harlowja"))

    def test_doas_ensure_append(self):
        self.patchUtils(self.tmp)
        util.write_file("/etc/doas.conf", "# root user\npermit nopass root\n")
        rules = [
            "permit nopass harlowja cmd ls",
            "permit nopass harlowja cmd pwd",
            "permit nopass harlowja cmd df",
        ]
        contents = self._write_load_doas("harlowja", rules)[0]
        self.assertIn("root", contents)
        self.assertEqual(2, contents.count("root"))
        self.assertIn("harlowja", contents)
        self.assertEqual(4, contents.count("harlowja"))

    def test_sudoers_ensure_rules(self):
        rules = "ALL=(ALL:ALL) ALL"
        contents = self._write_load_sudoers("harlowja", rules)[0]
        expected = ["harlowja ALL=(ALL:ALL) ALL"]
        self.assertEqual(len(expected), self._count_in(expected, contents))
        not_expected = [
            "harlowja A",
            "harlowja L",
            "harlowja L",
        ]
        self.assertEqual(0, self._count_in(not_expected, contents))

    def test_sudoers_ensure_rules_list(self):
        rules = [
            "ALL=(ALL:ALL) ALL",
            "B-ALL=(ALL:ALL) ALL",
            "C-ALL=(ALL:ALL) ALL",
        ]
        contents = self._write_load_sudoers("harlowja", rules)[0]
        expected = [
            "harlowja ALL=(ALL:ALL) ALL",
            "harlowja B-ALL=(ALL:ALL) ALL",
            "harlowja C-ALL=(ALL:ALL) ALL",
        ]
        self.assertEqual(len(expected), self._count_in(expected, contents))
        not_expected = [
            "harlowja A",
            "harlowja L",
            "harlowja L",
        ]
        self.assertEqual(0, self._count_in(not_expected, contents))

    def test_sudoers_ensure_handle_duplicates(self):
        rules = [
            "ALL=(ALL:ALL) ALL",
            "B-ALL=(ALL:ALL) ALL",
            "C-ALL=(ALL:ALL) ALL",
        ]
        d = self._write_load_sudoers("harlowja", rules)[2]
        # write to sudoers again - should not create duplicate rules
        d.write_sudo_rules("harlowja", rules)
        contents = util.load_text_file(d.ci_sudoers_fn)
        expected = [
            "harlowja ALL=(ALL:ALL) ALL",
            "harlowja B-ALL=(ALL:ALL) ALL",
            "harlowja C-ALL=(ALL:ALL) ALL",
        ]
        self.assertEqual(len(expected), self._count_in(expected, contents))
        not_expected = [
            "harlowja A",
            "harlowja L",
            "harlowja L",
        ]
        self.assertEqual(0, self._count_in(not_expected, contents))

    def test_sudoers_ensure_new(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        d.ensure_sudo_dir("/b")
        contents = util.load_text_file("/etc/sudoers")
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))

    def test_sudoers_ensure_append(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        util.write_file("/etc/sudoers", "josh, josh\n")
        d.ensure_sudo_dir("/b")
        contents = util.load_text_file("/etc/sudoers")
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))
        self.assertIn("josh", contents)
        self.assertEqual(2, contents.count("josh"))
        self.assertIn(
            "Added '#includedir /b' to /etc/sudoers", self.logs.getvalue()
        )

    def test_sudoers_ensure_append_sudoer_file(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        util.write_file("/etc/sudoers", "josh, josh\n")
        d.ensure_sudo_dir("/b", "/etc/sudoers")
        contents = util.load_text_file("/etc/sudoers")
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))
        self.assertIn("josh", contents)
        self.assertEqual(2, contents.count("josh"))

    def test_usr_sudoers_ensure_new(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        util.write_file("/usr/etc/sudoers", "josh, josh\n")
        d.ensure_sudo_dir("/b")
        contents = util.load_text_file("/etc/sudoers")
        self.assertIn("josh", contents)
        self.assertEqual(2, contents.count("josh"))
        self.assertIn("includedir /b", contents)
        self.assertTrue(os.path.isdir("/b"))
        self.assertIn(
            "Using content from '/usr/etc/sudoers", self.logs.getvalue()
        )

    def test_usr_sudoers_ensure_no_etc_create_when_include_in_usr_etc(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        util.write_file("/usr/etc/sudoers", "#includedir /b")
        d.ensure_sudo_dir("/b")
        self.assertTrue(not os.path.exists("/etc/sudoers"))

    def test_sudoers_ensure_only_one_includedir(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        for char in ["#", "@"]:
            util.write_file("/etc/sudoers", "{}includedir /b".format(char))
            d.ensure_sudo_dir("/b")
            contents = util.load_text_file("/etc/sudoers")
            self.assertIn("includedir /b", contents)
            self.assertTrue(os.path.isdir("/b"))
            self.assertEqual(1, contents.count("includedir /b"))

    def test_arch_package_mirror_info_unknown(self):
        """for an unknown arch, we should get back that with arch 'default'."""
        arch_mirrors = gapmi(package_mirrors, arch="unknown")
        self.assertEqual(unknown_arch_info, arch_mirrors)

    def test_arch_package_mirror_info_known(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        self.assertEqual(package_mirrors[0], arch_mirrors)

    def test_systemd_in_use(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        os.makedirs("/run/systemd/system")
        self.assertTrue(d.uses_systemd())

    def test_systemd_not_in_use(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        self.assertFalse(d.uses_systemd())

    def test_systemd_symlink(self):
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        self.patchOS(self.tmp)
        self.patchUtils(self.tmp)
        os.makedirs("/run/systemd")
        os.symlink("/", "/run/systemd/system")
        self.assertFalse(d.uses_systemd())

    @mock.patch("cloudinit.distros.debian.read_system_locale")
    def test_get_locale_ubuntu(self, m_locale):
        """Test ubuntu distro returns locale set to C.UTF-8"""
        m_locale.return_value = "C.UTF-8"
        cls = distros.fetch("ubuntu")
        d = cls("ubuntu", {}, None)
        locale = d.get_locale()
        self.assertEqual("C.UTF-8", locale)

    @mock.patch("cloudinit.distros.rhel.Distro._read_system_locale")
    def test_get_locale_rhel(self, m_locale):
        """Test rhel distro returns locale set to C.UTF-8"""
        m_locale.return_value = "C.UTF-8"
        cls = distros.fetch("rhel")
        d = cls("rhel", {}, None)
        locale = d.get_locale()
        self.assertEqual("C.UTF-8", locale)

    def test_expire_passwd_uses_chpasswd(self):
        """Test ubuntu.expire_passwd uses the passwd command."""
        for d_name in ("ubuntu", "rhel"):
            cls = distros.fetch(d_name)
            d = cls(d_name, {}, None)
            with mock.patch("cloudinit.subp.subp") as m_subp:
                d.expire_passwd("myuser")
            m_subp.assert_called_once_with(["passwd", "--expire", "myuser"])

    def test_expire_passwd_freebsd_uses_pw_command(self):
        """Test FreeBSD.expire_passwd uses the pw command."""
        cls = distros.fetch("freebsd")
        # patch ifconfig -a
        with mock.patch(
            "cloudinit.distros.networking.subp.subp", return_value=("", None)
        ):
            d = cls("freebsd", {}, None)
        with mock.patch("cloudinit.subp.subp") as m_subp:
            d.expire_passwd("myuser")
        m_subp.assert_called_once_with(
            ["pw", "usermod", "myuser", "-p", "01-Jan-1970"]
        )


class TestGetPackageMirrors:
    def return_first(self, mlist):
        if not mlist:
            return None
        return mlist[0]

    def return_second(self, mlist):
        if not mlist:
            return None

        return mlist[1] if len(mlist) > 1 else None

    def return_none(self, _mlist):
        return None

    def return_last(self, mlist):
        if not mlist:
            return None
        return mlist[-1]

    @pytest.mark.parametrize(
        "allow_ec2_mirror, platform_type, mirrors",
        [
            (
                True,
                "ec2",
                [
                    {
                        "primary": "http://us-east-1.ec2/",
                        "security": "http://security-mirror1-intel",
                    },
                    {
                        "primary": "http://us-east-1a.clouds/",
                        "security": "http://security-mirror2-intel",
                    },
                ],
            ),
            (
                True,
                "other",
                [
                    {
                        "primary": "http://us-east-1.ec2/",
                        "security": "http://security-mirror1-intel",
                    },
                    {
                        "primary": "http://us-east-1a.clouds/",
                        "security": "http://security-mirror2-intel",
                    },
                ],
            ),
            (
                False,
                "ec2",
                [
                    {
                        "primary": "http://us-east-1.ec2/",
                        "security": "http://security-mirror1-intel",
                    },
                    {
                        "primary": "http://us-east-1a.clouds/",
                        "security": "http://security-mirror2-intel",
                    },
                ],
            ),
            (
                False,
                "other",
                [
                    {
                        "primary": "http://us-east-1a.clouds/",
                        "security": "http://security-mirror1-intel",
                    },
                    {
                        "primary": "http://fs-primary-intel",
                        "security": "http://security-mirror2-intel",
                    },
                ],
            ),
        ],
    )
    def test_get_package_mirror_info_az_ec2(
        self, allow_ec2_mirror, platform_type, mirrors
    ):
        flag_path = (
            "cloudinit.distros.ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES"
        )
        with mock.patch(flag_path, allow_ec2_mirror):
            arch_mirrors = gapmi(package_mirrors, arch="amd64")
            data_source_mock = mock.Mock(
                availability_zone="us-east-1a", platform_type=platform_type
            )

            results = gpmi(
                arch_mirrors,
                data_source=data_source_mock,
                mirror_filter=self.return_first,
            )
            assert results == mirrors[0]

            results = gpmi(
                arch_mirrors,
                data_source=data_source_mock,
                mirror_filter=self.return_second,
            )
            assert results == mirrors[1]

            results = gpmi(
                arch_mirrors,
                data_source=data_source_mock,
                mirror_filter=self.return_none,
            )
            assert results == package_mirrors[0]["failsafe"]

    def test_get_package_mirror_info_az_non_ec2(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        data_source_mock = mock.Mock(availability_zone="nova.cloudvendor")

        results = gpmi(
            arch_mirrors,
            data_source=data_source_mock,
            mirror_filter=self.return_first,
        )
        assert results == {
            "primary": "http://nova.cloudvendor.clouds/",
            "security": "http://security-mirror1-intel",
        }

        results = gpmi(
            arch_mirrors,
            data_source=data_source_mock,
            mirror_filter=self.return_last,
        )
        assert results == {
            "primary": "http://nova.cloudvendor.clouds/",
            "security": "http://security-mirror2-intel",
        }

    def test_get_package_mirror_info_none(self):
        arch_mirrors = gapmi(package_mirrors, arch="amd64")
        data_source_mock = mock.Mock(availability_zone=None)

        # because both search entries here replacement based on
        # availability-zone, the filter will be called with an empty list and
        # failsafe should be taken.
        results = gpmi(
            arch_mirrors,
            data_source=data_source_mock,
            mirror_filter=self.return_first,
        )
        assert results == {
            "primary": "http://fs-primary-intel",
            "security": "http://security-mirror1-intel",
        }

        results = gpmi(
            arch_mirrors,
            data_source=data_source_mock,
            mirror_filter=self.return_last,
        )
        assert results == {
            "primary": "http://fs-primary-intel",
            "security": "http://security-mirror2-intel",
        }


@pytest.mark.usefixtures("fake_filesystem")
class TestDistro:
    @pytest.mark.parametrize("is_noexec", [False, True])
    @mock.patch(M_PATH + "util.has_mount_opt")
    @mock.patch(M_PATH + "temp_utils.get_tmp_ancestor", return_value="/tmp")
    def test_get_tmp_exec_path(
        self, m_get_tmp_ancestor, m_has_mount_opt, is_noexec, mocker
    ):
        m_has_mount_opt.return_value = not is_noexec
        cls = distros.fetch("ubuntu")
        distro = cls("ubuntu", {}, None)
        mocker.patch.object(distro, "usr_lib_exec", "/usr_lib_exec")
        tmp_path = distro.get_tmp_exec_path()
        if is_noexec:
            assert "/tmp" == tmp_path
        else:
            assert "/usr_lib_exec/cloud-init/clouddir" == tmp_path


@pytest.mark.parametrize(
    "chosen_client, config, which_override",
    [
        pytest.param(
            IscDhclient,
            {"network": {"dhcp_client_priority": ["dhclient"]}},
            None,
            id="single_client_is_found_from_config_dhclient",
        ),
        pytest.param(
            Udhcpc,
            {"network": {"dhcp_client_priority": ["udhcpc"]}},
            None,
            id="single_client_is_found_from_config_udhcpc",
        ),
        pytest.param(
            Dhcpcd,
            {"network": {"dhcp_client_priority": ["dhcpcd"]}},
            None,
            id="single_client_is_found_from_config_dhcpcd",
        ),
        pytest.param(
            Dhcpcd,
            {"network": {"dhcp_client_priority": ["dhcpcd", "dhclient"]}},
            None,
            id="first_client_is_found_from_config_dhcpcd",
        ),
        pytest.param(
            Udhcpc,
            {
                "network": {
                    "dhcp_client_priority": ["udhcpc", "dhcpcd", "dhclient"]
                }
            },
            None,
            id="first_client_is_found_from_config_udhcpc",
        ),
        pytest.param(
            Dhcpcd,
            {"network": {"dhcp_client_priority": []}},
            None,
            id="first_client_is_found_no_config_dhcpcd",
        ),
        pytest.param(
            Dhcpcd,
            {
                "network": {
                    "dhcp_client_priority": ["udhcpc", "dhcpcd", "dhclient"]
                }
            },
            [False, False, True, True],
            id="second_client_is_found_from_config_dhcpcd",
        ),
    ],
)
class TestDHCP:
    @mock.patch("cloudinit.net.dhcp.subp.which")
    def test_dhcp_configuration(
        self, m_which, chosen_client, config, which_override
    ):
        """check that, when a user provides a configuration at
        network.dhcp_client_priority, the correct client is chosen
        """
        m_which.side_effect = which_override
        distro = Distro("", {}, {})
        distro._cfg = config
        assert isinstance(distro.dhcp_client, chosen_client)
