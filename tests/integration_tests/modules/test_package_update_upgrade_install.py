# This file is part of cloud-init. See LICENSE file for license information.
"""Integration test for the package update upgrade install module.

This test module asserts that packages are upgraded/updated during boot
with the ``package_update_upgrade_install`` module. We are also testing
if we can install new packages during boot too.
"""

import re

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
packages:
  - sl
  - apt:
    - tree
  - snap:
    - curl
  - postman
package_update: true
package_upgrade: true
"""


@pytest.mark.skipif(not IS_UBUNTU, reason="Uses Apt")
@pytest.mark.user_data(USER_DATA)
class TestPackageUpdateUpgradeInstall:
    def assert_apt_package_installed(self, pkg_out, name, version=None):
        """Check dpkg-query --show output for matching package name.

        @param name: package base name
        @param version: string representing a package version or part of a
            version.
        """
        pkg_match = re.search(
            "^%s\t(?P<version>.*)$" % name, pkg_out, re.MULTILINE
        )
        if pkg_match:
            installed_version = pkg_match.group("version")
            if not version:
                return  # Success
            if installed_version.startswith(version):
                return  # Success
            raise AssertionError(
                "Expected package version %s-%s not found. Found %s" % name,
                version,
                installed_version,
            )
        raise AssertionError(f"Package not installed: {name}")

    def test_apt_packages_are_installed(self, class_client):
        pkg_out = class_client.execute("dpkg-query --show")

        self.assert_apt_package_installed(pkg_out, "sl")
        self.assert_apt_package_installed(pkg_out, "tree")

    def test_apt_packages_were_updated(self, class_client):
        out = class_client.execute(
            "grep ^Commandline: /var/log/apt/history.log"
        )
        assert re.search(
            "Commandline: /usr/bin/apt-get --option=Dpkg::Options"
            "::=--force-confold --option=Dpkg::options::=--force-unsafe-io "
            r"--assume-yes --quiet install (sl|tree) (tree|sl)",
            out,
        )

    def test_apt_packages_were_upgraded(self, class_client):
        """Test cloud-init-output for install & upgrade stuff."""
        out = class_client.read_from_file("/var/log/cloud-init-output.log")
        assert "Setting up tree (" in out
        assert "Setting up sl (" in out
        assert "Reading package lists..." in out
        assert "Building dependency tree..." in out
        assert "Reading state information..." in out
        assert "Calculating upgrade..." in out

    def test_snap_packages_are_installed(self, class_client):
        output = class_client.execute("snap list")
        assert "curl" in output
        assert "postman" in output


HELLO_VERSIONS_BY_RELEASE = {
    "oracular": "2.10-3build2",
    "noble": "2.10-3build1",
    "mantic": "2.10-3",
    "lunar": "2.10-3",
    "jammy": "2.10-2ubuntu4",
    "focal": "2.10-2ubuntu2",
}

VERSIONED_USER_DATA = """\
#cloud-config
packages:
- [hello, {pkg_version}]
"""


@pytest.mark.skipif(not IS_UBUNTU, reason="Uses Apt")
def test_versioned_packages_are_installed(session_cloud: IntegrationCloud):
    pkg_version = HELLO_VERSIONS_BY_RELEASE.get(
        CURRENT_RELEASE.series, "2.10-3build1"
    )
    with session_cloud.launch(
        user_data=VERSIONED_USER_DATA.format(pkg_version=pkg_version)
    ) as client:
        verify_clean_log(client.read_from_file("/var/log/cloud-init.log"))
        assert f"hello	{pkg_version}" == client.execute(
            "dpkg-query -W hello"
        ), (
            "If this is failing for a new release, add it to "
            "HELLO_VERSIONS_BY_RELEASE"
        )
