"""Integration test for LP: #2013967.

Assert cloud-init will explicitly set 640 perms across reboot regardless
prior permissions. This is to avoid repeated security issues where sensitive
data has been leaked by various clouds into a world-readable
/var/log/cloud-init.log. We no longer wish to preserve too permissive
a set of permissions by cloud-init runtime which were established by
default log permissions by python's logging setup.
"""


def _get_log_perms(client):
    return client.execute("stat -c %a /var/log/cloud-init.log")


class TestLogPermissionsNotResetOnReboot:
    def test_permissions_unchanged(self, client):
        # Confirm that the current permissions aren't 644
        assert "640" == _get_log_perms(client)

        # Set permissions to 644 and confirm our assertion that
        # permissions are reset across reboot
        client.execute("chmod 644 /var/log/cloud-init.log")
        assert "644" == _get_log_perms(client)

        # Reboot
        client.restart()
        assert client.execute("cloud-init status").ok

        # Check that permissions are reset on reboot
        assert "640" == _get_log_perms(client)
