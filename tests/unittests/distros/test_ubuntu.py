# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit.distros import fetch


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
        m_snap_upgrade_packges = mocker.patch(
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
            m_snap_upgrade_packges.assert_called_once()
        else:
            m_snap_upgrade_packges.assert_not_called()
