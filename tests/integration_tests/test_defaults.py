"""Tests here shouldn't require any sort of user data or instance setup."""

import pytest

from tests.integration_tests import releases
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import (
    get_inactive_modules,
    verify_clean_boot,
    verify_clean_log,
)


@pytest.mark.ci
class TestDefaults:
    def test_clean_log(self, class_client: IntegrationInstance):
        log = class_client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log, ignore_deprecations=False)
        verify_clean_boot(class_client)

    def test_inactive_modules(self, class_client: IntegrationInstance):
        """Verify no errors, no deprecations and correct inactive modules in
        log.
        """
        log = class_client.read_from_file("/var/log/cloud-init.log")

        expected_inactive = {
            "apt_pipelining",
            "ansible",
            "bootcmd",
            "ca_certs",
            "chef",
            "disable_ec2_metadata",
            "disk_setup",
            "fan",
            "keyboard",
            "landscape",
            "lxd",
            "mcollective",
            "ntp",
            "package_update_upgrade_install",
            "phone_home",
            "power_state_change",
            "puppet",
            "rsyslog",
            "runcmd",
            "salt_minion",
            "snap",
            "timezone",
            "ubuntu_autoinstall",
            "ubuntu_pro",
            "ubuntu_drivers",
            "update_etc_hosts",
            "wireguard",
            "write_files",
            "write_files_deferred",
        }
        if releases.CURRENT_RELEASE >= releases.PLUCKY:
            expected_inactive.add("grub_dpkg")

        # Remove modules that run independent from user-data
        if class_client.settings.PLATFORM == "azure":
            expected_inactive.discard("disk_setup")
        elif class_client.settings.PLATFORM == "gce":
            expected_inactive.discard("ntp")
        elif class_client.settings.PLATFORM == "lxd_vm":
            if class_client.settings.OS_IMAGE == "bionic":
                expected_inactive.discard("write_files")
                expected_inactive.discard("write_files_deferred")
        elif class_client.settings.PLATFORM == "oci":
            expected_inactive.discard("update_etc_hosts")

        diff = expected_inactive.symmetric_difference(
            get_inactive_modules(log)
        )
        assert (
            not diff
        ), f"Expected inactive modules do not match, diff: {diff}"

    def test_var_log_cloud_init_output_not_world_readable(
        self, class_client: IntegrationInstance
    ):
        """
        The log can contain sensitive data, it shouldn't be world-readable.

        LP: #1918303
        """
        client = class_client
        # Check the file exists
        assert client.execute("test -f /var/log/cloud-init-output.log").ok

        # Check its permissions are as we expect
        perms, user, group = client.execute(
            "stat -c %a:%U:%G /var/log/cloud-init-output.log"
        ).split(":")
        assert "640" == perms
        assert "root" == user
        assert "adm" == group
