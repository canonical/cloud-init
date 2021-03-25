"""Integration tests relating to cloud-init's logging."""


class TestVarLogCloudInitOutput:
    """Integration tests relating to /var/log/cloud-init-output.log."""

    def test_var_log_cloud_init_output_not_world_readable(self, client):
        """
        The log can contain sensitive data, it shouldn't be world-readable.

        LP: #1918303
        """
        # Check the file exists
        assert client.execute("test -f /var/log/cloud-init-output.log").ok

        # Check its permissions are as we expect
        perms, user, group = client.execute(
            "stat -c %a:%U:%G /var/log/cloud-init-output.log"
        ).split(":")
        assert "640" == perms
        assert "root" == user
        assert "adm" == group
