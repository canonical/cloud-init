# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit.distros import fetch
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import mock

M_PATH = "cloudinit.distros.raspberry_pi_os."


class TestRaspberryPiOS:
    @mock.patch(M_PATH + "subp.subp")
    def test_set_keymap_calls_imager_custom(self, m_subp):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        distro.set_keymap("us", "pc105", "basic", "")
        m_subp.assert_called_once_with(
            ["/usr/lib/raspberrypi-sys-mods/imager_custom", "set_keymap", "us"]
        )

    @mock.patch(M_PATH + "subp.subp")
    def test_apply_locale_happy_path(self, m_subp):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        distro.apply_locale("en_GB.UTF-8")
        m_subp.assert_called_once_with(
            [
                "/usr/bin/raspi-config",
                "nonint",
                "do_change_locale",
                "en_GB.UTF-8",
            ]
        )

    @mock.patch(M_PATH + "subp.subp")
    def test_apply_locale_fallback_to_utf8(self, m_subp):
        m_subp.side_effect = [
            ProcessExecutionError("Invalid locale"),  # Simulate failure
            None,  # Fallback succeeds
        ]
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        distro.apply_locale("en_GB")
        assert m_subp.call_count == 2
        m_subp.assert_any_call(
            ["/usr/bin/raspi-config", "nonint", "do_change_locale", "en_GB"]
        )
        m_subp.assert_any_call(
            [
                "/usr/bin/raspi-config",
                "nonint",
                "do_change_locale",
                "en_GB.UTF-8",
            ]
        )

    @mock.patch(M_PATH + "subp.subp")
    def test_add_user_happy_path(self, m_subp):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        # Mock the superclass add_user to return True
        with mock.patch(
            "cloudinit.distros.debian.Distro.add_user", return_value=True
        ):
            assert distro.add_user("pi") is True
            m_subp.assert_called_once_with(
                ["/usr/bin/rename-user", "-f", "-s"],
                update_env={"SUDO_USER": "pi"},
            )

    @mock.patch(M_PATH + "subp.subp")
    def test_add_user_existing_user(self, m_subp):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        with mock.patch(
            "cloudinit.distros.debian.Distro.add_user", return_value=False
        ):
            assert distro.add_user("pi") is False
            m_subp.assert_not_called()

    @mock.patch(
        M_PATH + "subp.subp",
        side_effect=ProcessExecutionError("rename-user failed"),
    )
    @mock.patch("cloudinit.distros.debian.Distro.add_user", return_value=True)
    def test_add_user_rename_fails_logs_error(
        self, m_super_add_user, m_subp, caplog
    ):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)

        with caplog.at_level(logging.ERROR):
            assert distro.add_user("pi") is False
            assert "Failed to setup user" in caplog.text
