# This file is part of cloud-init. See LICENSE file for license information.
import logging

import pytest

from cloudinit.distros import fetch
from cloudinit.subp import SubpResult


class TestPackageCommand:
    @pytest.mark.parametrize("snap_available", (True, False))
    def test_package_command_only_refresh_snap_when_available(
        self, snap_available, mocker
    ):
        """Avoid calls to snap refresh when snap command not available."""
        m_snap_available = mocker.patch(
            "cloudinit.distros.ubuntu.Snap.available",
            return_value=snap_available,
        )
        m_snap_upgrade_packages = mocker.patch(
            "cloudinit.distros.ubuntu.Snap.upgrade_packages",
            return_value=snap_available,
        )
        m_apt_run_package_command = mocker.patch(
            "cloudinit.distros.package_management.apt.Apt.run_package_command",
        )
        cls = fetch("ubuntu")
        distro = cls("ubuntu", {}, None)
        distro.package_command("upgrade")
        m_apt_run_package_command.assert_called_once_with("upgrade")
        m_snap_available.assert_called_once()
        if snap_available:
            m_snap_upgrade_packages.assert_called_once()
        else:
            m_snap_upgrade_packages.assert_not_called()

    @pytest.mark.parametrize(
        "subp_side_effect,expected_log",
        (
            pytest.param(
                [
                    SubpResult(
                        stdout='{"refresh": {"hold": "forever"}}', stderr=None
                    )
                ],
                "Skipping snap refresh because refresh.hold is set to"
                " 'forever'",
                id="skip_snap_refresh_due_to_global_hold_forever",
            ),
            pytest.param(
                [
                    SubpResult(
                        stdout=(
                            '{"refresh": {"hold":'
                            ' "2024-07-08T15:38:20-06:00"}}'
                        ),
                        stderr=None,
                    ),
                    SubpResult(stdout="All snaps up to date.", stderr=""),
                ],
                "",
                id="perform_snap_refresh_due_to_temporary_global_hold",
            ),
            pytest.param(
                [
                    SubpResult(
                        stdout="{}",
                        stderr=(
                            'error: snap "core" has no "refresh.hold" '
                            "configuration option"
                        ),
                    ),
                    SubpResult(stdout="All snaps up to date.", stderr=""),
                ],
                "",
                id="snap_refresh_performed_when_no_global_hold_is_set",
            ),
        ),
    )
    def test_package_command_avoids_snap_refresh_when_refresh_hold_is_forever(
        self, subp_side_effect, expected_log, caplog, mocker
    ):
        """Do not call snap refresh when snap refresh.hold is forever.

        This indicates an environment where snaps refreshes are not preferred
        for whatever reason.
        """
        m_snap_available = mocker.patch(
            "cloudinit.distros.ubuntu.Snap.available",
            return_value=True,
        )
        m_subp = mocker.patch(
            "cloudinit.subp.subp",
            side_effect=subp_side_effect,
        )
        m_apt_run_package_command = mocker.patch(
            "cloudinit.distros.package_management.apt.Apt.run_package_command",
        )
        cls = fetch("ubuntu")
        distro = cls("ubuntu", {}, None)
        with caplog.at_level(logging.INFO):
            distro.package_command("upgrade")
        m_apt_run_package_command.assert_called_once_with("upgrade")
        m_snap_available.assert_called_once()
        expected_calls = [mocker.call(["snap", "get", "system", "-d"])]
        if expected_log:
            assert expected_log in caplog.text
        else:
            expected_calls.append(mocker.call(["snap", "refresh"]))
        assert m_subp.call_args_list == expected_calls
