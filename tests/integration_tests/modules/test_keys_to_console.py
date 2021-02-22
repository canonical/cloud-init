"""Integration tests for the cc_keys_to_console module.

(This is ported from
``tests/cloud_tests/testcases/modules/keys_to_console.yaml``.)"""
import pytest

BLACKLIST_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
ssh_key_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
"""

DISABLED_USER_DATA = """\
#cloud-config
ssh:
  emit_keys_to_console: false
"""


@pytest.mark.user_data(BLACKLIST_USER_DATA)
class TestKeysToConsoleBlacklist:
    """Test that the blacklist options work as expected."""
    @pytest.mark.parametrize("key_type", ["DSA", "ECDSA"])
    def test_excluded_keys(self, class_client, key_type):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "({})".format(key_type) not in syslog

    @pytest.mark.parametrize("key_type", ["ED25519", "RSA"])
    def test_included_keys(self, class_client, key_type):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "({})".format(key_type) in syslog


@pytest.mark.user_data(DISABLED_USER_DATA)
class TestKeysToConsoleDisabled:
    """Test that output can be fully disabled."""
    @pytest.mark.parametrize("key_type", ["DSA", "ECDSA", "ED25519", "RSA"])
    def test_keys_excluded(self, class_client, key_type):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "({})".format(key_type) not in syslog

    def test_header_excluded(self, class_client):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "BEGIN SSH HOST KEY FINGERPRINTS" not in syslog

    def test_footer_excluded(self, class_client):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "END SSH HOST KEY FINGERPRINTS" not in syslog
