# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit.distros import fetch
from cloudinit.subp import ProcessExecutionError
from tests.unittests.helpers import mock

M_PATH = "cloudinit.distros.raspberry_pi_os."


class TestRaspberryPiOS:
    @mock.patch("cloudinit.distros.debian.Distro.set_keymap")
    @mock.patch(M_PATH + "subp.subp")
    @mock.patch(M_PATH + "subp.which", return_value=False)
    def test_set_keymap_writes_file_and_runs_basics(
        self, m_which, m_subp, m_set_keymap
    ):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)

        args = [
            "gb",
            "pc105",
            "",
            "grp:alt_shift_toggle",
        ]

        # Avoid touching real services
        with mock.patch.object(cls, "manage_service") as m_manage_service:
            distro.set_keymap(*args)

            m_manage_service.assert_called_once_with(
                "restart", "keyboard-setup"
            )

        m_set_keymap.assert_called_once_with(*args)

        # Two raspi-config calls are always expected
        m_subp.assert_any_call(
            ["/usr/bin/raspi-config", "nonint", "update_labwc_keyboard"],
        )
        m_subp.assert_any_call(
            [
                "/usr/bin/raspi-config",
                "nonint",
                "update_squeekboard",
                "restart",
            ],
        )

        # No optional tools available, so only the two calls above
        assert m_subp.call_count == 2

    @mock.patch("cloudinit.distros.debian.Distro.set_keymap")
    @mock.patch(M_PATH + "subp.subp")
    def test_set_keymap_triggers_udevadm_when_available(
        self, m_subp, m_set_keymap
    ):
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)

        # Only udevadm available
        def which_side_effect(name):
            return name == "udevadm"

        with mock.patch(M_PATH + "subp.which", side_effect=which_side_effect):
            with mock.patch.object(cls, "manage_service"):
                distro.set_keymap("de", "pc105", "nodeadkeys", "")

        m_set_keymap.assert_called_once_with("de", "pc105", "nodeadkeys", "")

        # Expect 3 subp calls: two raspi-config + one udevadm trigger
        assert m_subp.call_count == 3
        m_subp.assert_any_call(
            [
                "udevadm",
                "trigger",
                "--subsystem-match=input",
                "--action=change",
            ],
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

    @mock.patch(
        "cloudinit.net.generate_fallback_config",
        return_value={"version": 1, "config": "fake"},
    )
    def test_fallback_netcfg(self, m_fallback_cfg, caplog):
        """Avoid fallback network unless disable_fallback_netcfg is False."""
        cls = fetch("raspberry_pi_os")
        distro = cls("raspberry-pi-os", {}, None)
        key = "disable_fallback_netcfg"
        expected_log_line = (
            "Skipping generation of fallback network "
            "config as per configuration. "
            "Rely on Raspberry Pi OS's default network configuration."
        )

        # The default skips fallback network config when no setting is given.
        caplog.clear()
        assert distro.generate_fallback_config() is None
        assert expected_log_line in caplog.text

        caplog.clear()
        distro._cfg[key] = True
        assert distro.generate_fallback_config() is None
        assert expected_log_line in caplog.text

        caplog.clear()
        distro._cfg[key] = False
        assert distro.generate_fallback_config() == {
            "version": 1,
            "config": "fake",
        }
        assert expected_log_line not in caplog.text
