"""Integration tests for the cc_keys_to_console module.

(This is ported from
``tests/cloud_tests/testcases/modules/keys_to_console.yaml``.)"""
import pytest

from tests.integration_tests.util import retry

BLACKLIST_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
ssh_key_console_blacklist: [ssh-dss, ssh-dsa, ecdsa-sha2-nistp256]
"""

BLACKLIST_ALL_KEYS_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ssh-dsa, ssh-ecdsa, ssh-ed25519, ssh-rsa, ssh-dss, ecdsa-sha2-nistp256]
"""  # noqa: E501

DISABLED_USER_DATA = """\
#cloud-config
ssh:
  emit_keys_to_console: false
"""

ENABLE_KEYS_TO_CONSOLE_USER_DATA = """\
#cloud-config
ssh:
  emit_keys_to_console: true
users:
 - default
 - name: barfoo
"""


@pytest.mark.user_data(BLACKLIST_USER_DATA)
class TestKeysToConsoleBlacklist:
    """Test that the blacklist options work as expected."""

    @pytest.mark.parametrize("key_type", ["DSA", "ECDSA"])
    def test_excluded_keys(self, class_client, key_type):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "({})".format(key_type) not in syslog

    # retry decorator here because it can take some time to be reflected
    # in syslog
    @retry(tries=30, delay=1)
    @pytest.mark.parametrize("key_type", ["ED25519", "RSA"])
    def test_included_keys(self, class_client, key_type):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "({})".format(key_type) in syslog


@pytest.mark.user_data(BLACKLIST_ALL_KEYS_USER_DATA)
class TestAllKeysToConsoleBlacklist:
    """Test that when key blacklist contains all key types that
    no header/footer are output.
    """

    def test_header_excluded(self, class_client):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "BEGIN SSH HOST KEY FINGERPRINTS" not in syslog

    def test_footer_excluded(self, class_client):
        syslog = class_client.read_from_file("/var/log/syslog")
        assert "END SSH HOST KEY FINGERPRINTS" not in syslog


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


@pytest.mark.user_data(ENABLE_KEYS_TO_CONSOLE_USER_DATA)
@pytest.mark.ec2
@pytest.mark.lxd_container
@pytest.mark.oci
@pytest.mark.openstack
class TestKeysToConsoleEnabled:
    """Test that output can be enabled disabled."""

    def test_duplicate_messaging_console_log(self, class_client):
        class_client.execute("cloud-init status --wait --long").ok
        try:
            console_log = class_client.instance.console_log()
        except NotImplementedError:
            # Assume that an exception here means that we can't use the console
            # log
            pytest.skip("NotImplementedError when requesting console log")
            return
        if console_log.lower() == "no console output":
            # This test retries because we might not have the full console log
            # on the first fetch. However, if we have no console output
            # at all, we don't want to keep retrying as that would trigger
            # another 5 minute wait on the pycloudlib side, which could
            # leave us waiting for a couple hours
            pytest.fail("no console output")
            return
        msg = "no authorized SSH keys fingerprints found for user barfoo."
        assert 1 == console_log.count(msg)
