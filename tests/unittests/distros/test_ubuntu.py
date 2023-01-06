# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

import pytest

from cloudinit import distros


class TestInstallPackages:
    @pytest.fixture(autouse=True)
    def setup(self, mocker):
        mocker.patch("cloudinit.subp.which", return_value=True)
        self.m_install = mocker.patch(
            "cloudinit.distros.debian.Distro.install_packages"
        )
        self.m_package = mocker.patch(
            "cloudinit.distros.debian.Distro.package_command"
        )
        mocker.patch("cloudinit.distros.debian.Distro.update_package_sources")
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_apt_packages",
            return_value=[],
        )
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_snap_packages",
            return_value=[],
        )
        self.m_subp = mocker.patch("cloudinit.subp.subp")
        self.distro = distros.fetch("ubuntu")("ubuntu", {}, None)

    def test_apt_and_snap_packages(self, mocker):
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_apt_packages",
            return_value=["apt1", "apt2"],
        )
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_snap_packages",
            return_value=["snap1", "snap2"],
        )

        self.distro.install_packages(["apt1", "snap1", "apt2", "snap2"])
        assert self.m_package.call_args == mock.call(
            "install", pkgs=["apt1", "apt2"]
        )
        assert self.m_subp.call_args_list == [
            mock.call(["snap", "install", "snap1"]),
            mock.call(["snap", "install", "snap2"]),
        ]

    def test_only_apt_packages(self, mocker):
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_apt_packages",
            return_value=["apt1", "apt2"],
        )
        self.distro.install_packages(["apt1", "apt2"])
        assert self.m_package.call_args == mock.call(
            "install", pkgs=["apt1", "apt2"]
        )
        assert self.m_subp.call_args is None

    def test_only_snap_packages(self, mocker):
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_snap_packages",
            return_value=["snap1", "snap2"],
        )

        self.distro.install_packages(["snap1", "snap2"])
        assert self.m_subp.call_args_list == [
            mock.call(["snap", "install", "snap1"]),
            mock.call(["snap", "install", "snap2"]),
        ]

        assert self.m_package.call_args is None

    def test_package_not_in_apt_or_snap(self, mocker):
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_apt_packages",
            return_value=["apt1", "apt2"],
        )
        mocker.patch(
            "cloudinit.distros.ubuntu.get_available_snap_packages",
            return_value=["snap1", "snap2"],
        )

        with pytest.raises(ValueError):
            self.distro.install_packages(
                ["apt1", "apt2", "snap1", "snap2", "OhNo"]
            )

    def test_snap_not_installed(self, mocker):
        mocker.patch("cloudinit.subp.which", return_value=False)
        self.distro.install_packages(["apt1", "apt2"])
        assert self.m_install.call_args == mock.call(["apt1", "apt2"])
