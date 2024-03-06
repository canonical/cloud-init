"""Integration tests for the cc_keys_to_console module.

(This is ported from
``tests/cloud_tests/testcases/modules/keys_to_console.yaml``.)"""
import pytest

from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import get_console_log

BLACKLIST_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ecdsa-sha2-nistp256]
ssh_key_console_blacklist: [ecdsa-sha2-nistp256]
"""

BLACKLIST_ALL_KEYS_USER_DATA = """\
#cloud-config
ssh_fp_console_blacklist: [ssh-ecdsa, ssh-ed25519, ssh-rsa, ecdsa-sha2-nistp256]
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

    @pytest.mark.parametrize("key_type", ["ECDSA"])
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

    @pytest.mark.parametrize("key_type", ["ECDSA", "ED25519", "RSA"])
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
@retry(tries=30, delay=1)
@pytest.mark.skipif(
    PLATFORM not in ["ec2", "lxd_container", "oci", "openstack"],
    reason=(
        "No Azure because no console log on Azure. "
        "Other platforms need testing."
    ),
)
def test_duplicate_messaging_console_log(client: IntegrationInstance):
    """Test that output can be enabled disabled."""
    assert (
        "no authorized SSH keys fingerprints found for user barfoo."
        in get_console_log(client)
    )
