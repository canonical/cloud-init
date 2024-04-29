# Copyright (C) 2020 Canonical Ltd.
#
# Author: Daniel Watkins <oddbloke@ubuntu.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Tests for cloudinit/distros/__init__.py"""

from unittest import mock

import pytest

from cloudinit.distros import (
    LDH_ASCII_CHARS,
    PackageInstallerError,
    _get_package_mirror_info,
)
from tests.unittests.distros import _get_distro

# In newer versions of Python, these characters will be omitted instead
# of substituted because of security concerns.
# See https://bugs.python.org/issue43882
SECURITY_URL_CHARS = "\n\r\t"

# Define a set of characters we would expect to be replaced
INVALID_URL_CHARS = [
    chr(x)
    for x in range(127)
    if chr(x) not in LDH_ASCII_CHARS + SECURITY_URL_CHARS
]
for separator in [":", ".", "/", "#", "?", "@", "[", "]"]:
    # Remove from the set characters that either separate hostname parts (":",
    # "."), terminate hostnames ("/", "#", "?", "@"), or cause Python to be
    # unable to parse URLs ("[", "]").
    INVALID_URL_CHARS.remove(separator)

M_PATH = "cloudinit.distros.package_management."


class TestGetPackageMirrorInfo:
    """
    Tests for cloudinit.distros._get_package_mirror_info.

    These supplement the tests in tests/unittests/test_distros/test_generic.py
    which are more focused on testing a single production-like configuration.
    These tests are more focused on specific aspects of the unit under test.
    """

    @pytest.mark.parametrize(
        "mirror_info,expected",
        [
            # Empty info gives empty return
            ({}, {}),
            # failsafe values used if present
            (
                {
                    "failsafe": {
                        "primary": "http://value",
                        "security": "http://other",
                    }
                },
                {"primary": "http://value", "security": "http://other"},
            ),
            # search values used if present
            (
                {
                    "search": {
                        "primary": ["http://value"],
                        "security": ["http://other"],
                    }
                },
                {"primary": ["http://value"], "security": ["http://other"]},
            ),
            # failsafe values used if search value not present
            (
                {
                    "search": {"primary": ["http://value"]},
                    "failsafe": {"security": "http://other"},
                },
                {"primary": ["http://value"], "security": "http://other"},
            ),
        ],
    )
    def test_get_package_mirror_info_failsafe(self, mirror_info, expected):
        """
        Test the interaction between search and failsafe inputs

        (This doesn't test the case where the mirror_filter removes all search
        options; test_failsafe_used_if_all_search_results_filtered_out covers
        that.)
        """
        assert expected == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: x
        )

    def test_failsafe_used_if_all_search_results_filtered_out(self):
        """Test the failsafe option used if all search options eliminated."""
        mirror_info = {
            "search": {"primary": ["http://value"]},
            "failsafe": {"primary": "http://other"},
        }
        assert {"primary": "http://other"} == _get_package_mirror_info(
            mirror_info, mirror_filter=lambda x: False
        )

    @pytest.mark.parametrize(
        "allow_ec2_mirror, platform_type", [(True, "ec2")]
    )
    @pytest.mark.parametrize(
        "availability_zone,region,patterns,expected",
        (
            # Test ec2_region alone
            (
                "fk-fake-1f",
                None,
                ["http://EC2-%(ec2_region)s/ubuntu"],
                ["http://ec2-fk-fake-1/ubuntu"],
            ),
            # Test availability_zone alone
            (
                "fk-fake-1f",
                None,
                ["http://AZ-%(availability_zone)s/ubuntu"],
                ["http://az-fk-fake-1f/ubuntu"],
            ),
            # Test region alone
            (
                None,
                "fk-fake-1",
                ["http://RG-%(region)s/ubuntu"],
                ["http://rg-fk-fake-1/ubuntu"],
            ),
            # Test that ec2_region is not available for non-matching AZs
            (
                "fake-fake-1f",
                None,
                [
                    "http://EC2-%(ec2_region)s/ubuntu",
                    "http://AZ-%(availability_zone)s/ubuntu",
                ],
                ["http://az-fake-fake-1f/ubuntu"],
            ),
            # Test that template order maintained
            (
                None,
                "fake-region",
                [
                    "http://RG-%(region)s-2/ubuntu",
                    "http://RG-%(region)s-1/ubuntu",
                ],
                [
                    "http://rg-fake-region-2/ubuntu",
                    "http://rg-fake-region-1/ubuntu",
                ],
            ),
            # Test that non-ASCII hostnames are IDNA encoded;
            # "IDNA-ТεЅТ̣".encode('idna') == b"xn--idna--4kd53hh6aba3q"
            (
                None,
                "ТεЅТ̣",
                ["http://www.IDNA-%(region)s.com/ubuntu"],
                ["http://www.xn--idna--4kd53hh6aba3q.com/ubuntu"],
            ),
            # Test that non-ASCII hostnames with a port are IDNA encoded;
            # "IDNA-ТεЅТ̣".encode('idna') == b"xn--idna--4kd53hh6aba3q"
            (
                None,
                "ТεЅТ̣",
                ["http://www.IDNA-%(region)s.com:8080/ubuntu"],
                ["http://www.xn--idna--4kd53hh6aba3q.com:8080/ubuntu"],
            ),
            # Test that non-ASCII non-hostname parts of URLs are unchanged
            (
                None,
                "ТεЅТ̣",
                ["http://www.example.com/%(region)s/ubuntu"],
                ["http://www.example.com/ТεЅТ̣/ubuntu"],
            ),
            # Test that IPv4 addresses are unchanged
            (
                None,
                "fk-fake-1",
                ["http://192.168.1.1:8080/%(region)s/ubuntu"],
                ["http://192.168.1.1:8080/fk-fake-1/ubuntu"],
            ),
            # Test that IPv6 addresses are unchanged
            (
                None,
                "fk-fake-1",
                ["http://[2001:67c:1360:8001::23]/%(region)s/ubuntu"],
                ["http://[2001:67c:1360:8001::23]/fk-fake-1/ubuntu"],
            ),
            # Test that unparseable URLs are filtered out of the mirror list
            (
                None,
                "inv[lid",
                [
                    "http://%(region)s.in.hostname/should/be/filtered",
                    "http://but.not.in.the.path/%(region)s",
                ],
                ["http://but.not.in.the.path/inv[lid"],
            ),
            (
                None,
                "-some-region-",
                ["http://-lead-ing.%(region)s.trail-ing-.example.com/ubuntu"],
                ["http://lead-ing.some-region.trail-ing.example.com/ubuntu"],
            ),
        )
        + tuple(
            # Dynamically generate a test case for each non-LDH
            # (Letters/Digits/Hyphen) ASCII character, testing that it is
            # substituted with a hyphen
            (
                None,
                "fk{0}fake{0}1".format(invalid_char),
                ["http://%(region)s/ubuntu"],
                ["http://fk-fake-1/ubuntu"],
            )
            for invalid_char in INVALID_URL_CHARS
        ),
    )
    def test_valid_substitution(
        self,
        allow_ec2_mirror,
        platform_type,
        availability_zone,
        region,
        patterns,
        expected,
    ):
        """Test substitution works as expected."""
        flag_path = (
            "cloudinit.distros.ALLOW_EC2_MIRRORS_ON_NON_AWS_INSTANCE_TYPES"
        )

        m_data_source = mock.Mock(
            availability_zone=availability_zone,
            region=region,
            platform_type=platform_type,
        )
        mirror_info = {"search": {"primary": patterns}}

        with mock.patch(flag_path, allow_ec2_mirror):
            ret = _get_package_mirror_info(
                mirror_info,
                data_source=m_data_source,
                mirror_filter=lambda x: x,
            )
        print(allow_ec2_mirror)
        print(platform_type)
        print(availability_zone)
        print(region)
        print(patterns)
        print(expected)
        assert {"primary": expected} == ret


class TestUpdatePackageSources:
    """Tests for cloudinit.distros.Distro.update_package_sources."""

    @pytest.mark.parametrize(
        "apt_error,snap_error,expected_logs",
        [
            pytest.param(
                RuntimeError("fail to find 'apt' command"),
                None,
                [
                    "Failed to update package using apt: fail to find 'apt'"
                    " command"
                ],
            ),
            pytest.param(
                None,
                RuntimeError("fail to find 'snap' command"),
                [
                    "Failed to update package using snap: fail to find 'snap'"
                    " command"
                ],
            ),
        ],
    )
    def test_log_errors_with_updating_package_source(
        self, apt_error, snap_error, expected_logs, mocker, caplog
    ):
        """Log error raised from any package_manager.update_package_sources."""
        mocker.patch(M_PATH + "apt.Apt.available", return_value=True)
        mocker.patch(M_PATH + "snap.Snap.available", return_value=True)
        mocker.patch(
            M_PATH + "apt.Apt.update_package_sources",
            side_effect=apt_error,
        )
        mocker.patch(
            M_PATH + "snap.Snap.update_package_sources",
            side_effect=snap_error,
        )
        _get_distro("ubuntu").update_package_sources()
        for log in expected_logs:
            assert log in caplog.text

    @pytest.mark.parametrize(
        "apt_available,snap_available,expected_logs",
        [
            pytest.param(
                True,
                False,
                ["Skipping update for package manager 'snap': not available."],
            ),
            pytest.param(
                False,
                True,
                ["Skipping update for package manager 'apt': not available."],
            ),
            pytest.param(
                False,
                False,
                [
                    "Skipping update for package manager 'apt': not"
                    " available.",
                    "Skipping update for package manager 'snap': not"
                    " available.",
                ],
            ),
        ],
    )
    def test_run_available_package_managers(
        self, apt_available, snap_available, expected_logs, mocker, caplog
    ):
        """Avoid update_package_sources on unavailable package managers"""

        mocker.patch(M_PATH + "apt.Apt.available", return_value=apt_available)
        mocker.patch(
            M_PATH + "snap.Snap.available",
            return_value=snap_available,
        )

        m_apt_update = mocker.patch(M_PATH + "apt.Apt.update_package_sources")
        m_snap_update = mocker.patch(
            M_PATH + "snap.Snap.update_package_sources"
        )
        _get_distro("ubuntu").update_package_sources()
        if not snap_available:
            m_snap_update.assert_not_called()
        else:
            m_snap_update.assert_called_once()
        if not apt_available:
            m_apt_update.assert_not_called()
        else:
            m_apt_update.assert_called_once()
        for log in expected_logs:
            assert log in caplog.text


class TestInstall:
    """Tests for cloudinit.distros.Distro.install_packages."""

    @pytest.fixture(autouse=True)
    def ensure_available(self, mocker):
        mocker.patch(M_PATH + "apt.Apt.available", return_value=True)
        mocker.patch(M_PATH + "snap.Snap.available", return_value=True)

    @pytest.fixture
    def m_apt_install(self, mocker):
        return mocker.patch(
            M_PATH + "apt.Apt.install_packages",
            return_value=[],
        )

    @pytest.fixture
    def m_snap_install(self, mocker):
        return mocker.patch(
            M_PATH + "snap.Snap.install_packages",
            return_value=[],
        )

    @pytest.fixture
    def m_subp(self, mocker):
        return mocker.patch(
            "cloudinit.distros.bsd.subp.subp", return_value=("", "")
        )

    def test_invalid_yaml(self, m_apt_install):
        """Test that an invalid YAML raises an exception."""
        with pytest.raises(ValueError):
            _get_distro("debian").install_packages([["invalid"]])
        m_apt_install.assert_not_called()

    def test_unknown_package_manager(self, m_apt_install, caplog):
        """Test that an unknown package manager raises an exception."""
        _get_distro("debian").install_packages(
            [{"apt": ["pkg1"]}, "pkg2", {"invalid": ["pkg3"]}]
        )
        assert (
            "Cannot install packages under 'invalid' as it is not a supported "
            "package manager!" in caplog.text
        )
        install_args = m_apt_install.call_args_list[0][0][0]
        assert "pkg1" in install_args
        assert "pkg2" in install_args
        assert "pkg3" not in install_args

    def test_non_default_package_manager(self, m_apt_install, m_snap_install):
        """Test success from package manager not supported by distro."""
        _get_distro("debian").install_packages(
            [{"apt": ["pkg1"]}, "pkg2", {"snap": ["pkg3"]}]
        )
        apt_install_args = m_apt_install.call_args_list[0][0][0]
        assert "pkg1" in apt_install_args
        assert "pkg2" in apt_install_args
        assert "pkg3" not in apt_install_args

        assert "pkg3" in m_snap_install.call_args_list[0][1]["pkglist"]

    def test_non_default_package_manager_fail(
        self, m_apt_install, mocker, caplog
    ):
        """Test fail from package manager not supported by distro."""
        m_snap_install = mocker.patch(
            M_PATH + "snap.Snap.install_packages",
            return_value=["pkg3"],
        )
        with pytest.raises(
            PackageInstallerError,
            match="Failed to install the following packages: {'pkg3'}",
        ):
            _get_distro("debian").install_packages(
                [{"apt": ["pkg1"]}, "pkg2", {"snap": ["pkg3"]}]
            )

        assert "pkg3" in m_snap_install.call_args_list[0][1]["pkglist"]

    def test_default_and_specific_package_manager(
        self, m_apt_install, m_snap_install
    ):
        """Test success from package manager not supported by distro."""
        _get_distro("ubuntu").install_packages(
            ["pkg1", ["pkg3", "ver3"], {"apt": [["pkg2", "ver2"]]}]
        )
        apt_install_args = m_apt_install.call_args_list[0][0][0]
        assert "pkg1" in apt_install_args
        assert ("pkg2", "ver2") in apt_install_args
        assert "pkg3" not in apt_install_args

        m_snap_install.assert_not_called()

    def test_specific_package_manager_fail_doesnt_retry(
        self, mocker, m_snap_install
    ):
        """Test fail from package manager doesn't retry as generic."""
        m_apt_install = mocker.patch(
            M_PATH + "apt.Apt.install_packages",
            return_value=["pkg1"],
        )
        with pytest.raises(PackageInstallerError):
            _get_distro("ubuntu").install_packages([{"apt": ["pkg1"]}])
        apt_install_args = m_apt_install.call_args_list[0][0][0]
        assert "pkg1" in apt_install_args
        m_snap_install.assert_not_called()

    def test_no_attempt_if_no_package_manager(
        self, mocker, m_apt_install, m_snap_install, caplog
    ):
        """Test that no attempt is made if there are no package manager."""
        mocker.patch(M_PATH + "apt.Apt.available", return_value=False)
        mocker.patch(M_PATH + "snap.Snap.available", return_value=False)
        with pytest.raises(PackageInstallerError):
            _get_distro("ubuntu").install_packages(
                ["pkg1", "pkg2", {"other": "pkg3"}]
            )
        m_apt_install.assert_not_called()
        m_snap_install.assert_not_called()

        assert "Package manager 'apt' not available" in caplog.text
        assert "Package manager 'snap' not available" in caplog.text

    @pytest.mark.parametrize(
        "distro,pkg_list,apt_available,apt_failed,snap_failed,total_failed",
        [
            pytest.param(
                "debian",
                ["pkg1", {"apt": ["pkg2"], "snap": ["pkg3"]}],
                False,
                [],
                ["pkg1", "pkg3"],
                ["pkg1", "pkg2", "pkg3"],
                id="debian_no_apt",
            ),
            pytest.param(
                "debian",
                ["pkg1", {"apt": ["pkg2"], "snap": ["pkg3"]}],
                True,
                ["pkg2"],
                ["pkg3"],
                ["pkg2", "pkg3"],
                id="debian_with_apt",
            ),
            pytest.param(
                "ubuntu",
                ["pkg1", {"apt": ["pkg2"], "snap": ["pkg3"]}],
                False,
                [],
                [],
                ["pkg2"],
                id="ubuntu_no_apt",
            ),
            pytest.param(
                "ubuntu",
                ["pkg1", {"apt": ["pkg2"], "snap": ["pkg3"]}],
                True,
                ["pkg1"],
                ["pkg3"],
                ["pkg3"],
                id="ubuntu_with_apt",
            ),
        ],
    )
    def test_failed(
        self,
        distro,
        pkg_list,
        apt_available,
        apt_failed,
        snap_failed,
        total_failed,
        mocker,
        m_apt_install,
        m_snap_install,
    ):
        """Test that failed packages are properly tracked.

        We need to ensure that the failed packages are properly tracked:
            1. When package install fails normally
            2. When package manager is not available
            3. When package manager is not explicitly supported by the distro

        So test various combinations of these scenarios.
        """
        mocker.patch(M_PATH + "apt.Apt.available", return_value=apt_available)
        mocker.patch(
            M_PATH + "apt.Apt.install_packages",
            return_value=apt_failed,
        )
        mocker.patch(
            M_PATH + "snap.Snap.install_packages",
            return_value=snap_failed,
        )
        with pytest.raises(PackageInstallerError) as exc:
            _get_distro(distro).install_packages(pkg_list)
        message = exc.value.args[0]
        assert "Failed to install the following packages" in message
        for pkg in total_failed:
            assert pkg in message
