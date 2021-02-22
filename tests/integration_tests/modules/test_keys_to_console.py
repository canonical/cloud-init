"""Integration tests for the cc_keys_to_console module.

(This is ported from
``tests/cloud_tests/testcases/modules/keys_to_console.yaml``.)"""
import pytest

BLACKLIST_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
ssh_key_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
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
