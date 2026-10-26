# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit import distros, util


class TestAlpineBusyboxUserGroup:
    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch("cloudinit.distros.subp.which", return_value=False)
    def test_busybox_add_group(self, m_which, m_subp):
        distro = distros.fetch("alpine")("alpine", {}, None)

        group = "mygroup"

        distro.create_group(group)

        m_subp.assert_called_with(["addgroup", group])

    @pytest.mark.parametrize(
        "create_kwargs,expected",
        [
            ({"gid": 1500}, ["addgroup", "-g", "1500", "mygroup"]),
            ({"system": True}, ["addgroup", "-S", "mygroup"]),
            (
                {"gid": 0, "system": True},
                ["addgroup", "-g", "0", "-S", "mygroup"],
            ),
        ],
    )
    @mock.patch("cloudinit.distros.alpine.util.is_group", return_value=False)
    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch("cloudinit.distros.subp.which", return_value=False)
    def test_busybox_add_group_options(
        self, m_which, m_subp, m_is_group, create_kwargs, expected
    ):
        distro = distros.fetch("alpine")("alpine", {}, None)

        distro.create_group("mygroup", **create_kwargs)

        assert [mock.call(expected)] == m_subp.call_args_list

    @pytest.mark.usefixtures("fake_filesystem")
    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch("cloudinit.distros.subp.which", return_value=False)
    def test_busybox_add_user(self, m_which, m_subp, tmpdir):
        distro = distros.fetch("alpine")("alpine", {}, None)

        shadow_file = tmpdir.join("/etc/shadow")
        shadow_file.dirpath().mkdir()

        user = "me2"

        # Need to place entry for user in /etc/shadow as
        # "adduser" is stubbed and so will not create it.
        root_entry = "root::19848:0:::::"
        shadow_file.write(
            root_entry + "\n" + user + ":!:19848:0:99999:7:::" + "\n"
        )

        distro.shadow_fn = shadow_file

        distro.add_user(user, groups=[], lock_passwd=True)

        m_subp.assert_called_with(
            ["adduser", "-D", user], logstring=["adduser", "-D", user]
        )

        contents = util.load_text_file(shadow_file)
        expected = root_entry + "\n" + user + ":!:19848::::::" + "\n"

        assert contents == expected


class TestAlpineShadowUserGroup:
    distro = distros.fetch("alpine")("alpine", {}, None)

    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch(
        "cloudinit.distros.subp.which", return_value=("/usr/sbin/groupadd")
    )
    def test_shadow_add_group(self, m_which, m_subp):
        group = "mygroup"

        self.distro.create_group(group)

        m_subp.assert_called_with(["groupadd", group])

    @mock.patch("cloudinit.distros.util.system_is_snappy", return_value=False)
    @mock.patch("cloudinit.distros.util.is_group", return_value=False)
    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch(
        "cloudinit.distros.subp.which", return_value=("/usr/sbin/groupadd")
    )
    def test_shadow_add_group_options(
        self, m_which, m_subp, m_is_group, m_is_snappy
    ):
        self.distro.create_group("mygroup", gid=1500, system=True)

        assert [
            mock.call(["groupadd", "mygroup", "--gid", "1500", "--system"])
        ] == m_subp.call_args_list

    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch(
        "cloudinit.distros.subp.which", return_value=("/usr/sbin/useradd")
    )
    def test_shadow_add_user(self, m_which, m_subp):
        user = "me2"

        self.distro.add_user(user, groups=[])

        m_subp.assert_called_with(
            ["useradd", user, "-m"], logstring=["useradd", user, "-m"]
        )
