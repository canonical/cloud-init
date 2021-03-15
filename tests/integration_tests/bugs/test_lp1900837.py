"""Integration test for LP: #1900836.

This test mirrors the reproducing steps from the reported bug: it changes the
permissions on cloud-init.log to 600 and confirms that they remain 600 after a
reboot.
"""
import pytest


def _get_log_perms(client):
    return client.execute("stat -c %a /var/log/cloud-init.log")


@pytest.mark.sru_2020_11
class TestLogPermissionsNotResetOnReboot:
    def test_permissions_unchanged(self, client):
        # Confirm that the current permissions aren't 600
        assert "644" == _get_log_perms(client)

        # Set permissions to 600 and confirm our assertion passes pre-reboot
        client.execute("chmod 600 /var/log/cloud-init.log")
        assert "600" == _get_log_perms(client)

        # Reboot
        client.restart()
        assert client.execute('cloud-init status').ok

        # Check that permissions are not reset on reboot
        assert "600" == _get_log_perms(client)
