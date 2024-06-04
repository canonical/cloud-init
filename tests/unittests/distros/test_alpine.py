# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit import distros, util
from tests.unittests.helpers import TestCase


class TestAlpineBusyboxUserGroup:
    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch("cloudinit.distros.subp.which", return_value=False)
    def test_busybox_add_group(self, m_which, m_subp):
        distro = distros.fetch("alpine")("alpine", {}, None)

        group = "mygroup"

        distro.create_group(group)

        m_subp.assert_called_with(["addgroup", group])

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

        distro.add_user(user, lock_passwd=True)

        m_subp.assert_called_with(["adduser", "-D", user])

        contents = util.load_text_file(shadow_file)
        expected = root_entry + "\n" + user + ":!:19848::::::" + "\n"

        assert contents == expected


class TestAlpineShadowUserGroup(TestCase):
    distro = distros.fetch("alpine")("alpine", {}, None)

    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch(
        "cloudinit.distros.subp.which", return_value=("/usr/sbin/groupadd")
    )
    def test_shadow_add_group(self, m_which, m_subp):
        group = "mygroup"

        self.distro.create_group(group)

        m_subp.assert_called_with(["groupadd", group])

    @mock.patch("cloudinit.distros.alpine.subp.subp")
    @mock.patch(
        "cloudinit.distros.subp.which", return_value=("/usr/sbin/useradd")
    )
    def test_shadow_add_user(self, m_which, m_subp):
        user = "me2"

        self.distro.add_user(user)

        m_subp.assert_called_with(
            ["useradd", user, "-m"], logstring=["useradd", user, "-m"]
        )
