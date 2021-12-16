"""Integration test for the package update upgrade install module.

This test module asserts that packages are upgraded/updated during boot
with the ``package_update_upgrade_install`` module. We are also testing
if we can install new packages during boot too.

(This is ported from
``tests/cloud_tests/testcases/modules/package_update_upgrade_install.yaml``.)

NOTE: the testcase for this looks for the command in history.log as
      /usr/bin/apt-get..., which is not how it always appears. it should
      instead look for just apt-get...
"""

import re

import pytest

USER_DATA = """\
#cloud-config
packages:
  - sl
  - tree
package_update: true
package_upgrade: true
"""


@pytest.mark.ubuntu
@pytest.mark.user_data(USER_DATA)
class TestPackageUpdateUpgradeInstall:
    def assert_package_installed(self, pkg_out, name, version=None):
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
        raise AssertionError("Package not installed: %s" % name)

    def test_new_packages_are_installed(self, class_client):
        pkg_out = class_client.execute("dpkg-query --show")

        self.assert_package_installed(pkg_out, "sl")
        self.assert_package_installed(pkg_out, "tree")

    def test_packages_were_updated(self, class_client):
        out = class_client.execute(
            "grep ^Commandline: /var/log/apt/history.log"
        )
        assert (
            "Commandline: /usr/bin/apt-get --option=Dpkg::Options"
            "::=--force-confold --option=Dpkg::options::=--force-unsafe-io "
            "--assume-yes --quiet install sl tree" in out
        )

    def test_packages_were_upgraded(self, class_client):
        """Test cloud-init-output for install & upgrade stuff."""
        out = class_client.read_from_file("/var/log/cloud-init-output.log")
        assert "Setting up tree (" in out
        assert "Setting up sl (" in out
        assert "Reading package lists..." in out
        assert "Building dependency tree..." in out
        assert "Reading state information..." in out
        assert "Calculating upgrade..." in out
