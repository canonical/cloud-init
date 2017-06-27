# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestSshKeyFingerprintsDisable(base.CloudTestCase):
    """Test ssh key fingerprints module."""

    def test_cloud_init_log(self):
        """Verify disabled."""
        out = self.get_data_file('cloud-init.log')
        self.assertIn('Skipping module named ssh-authkey-fingerprints, '
                      'logging of ssh fingerprints disabled', out)

    def test_syslog(self):
        """Verify output of syslog."""
        out = self.get_data_file('syslog')
        self.assertNotRegex(out, r'256 SHA256:.*(ECDSA)')
        self.assertNotRegex(out, r'256 SHA256:.*(ED25519)')
        self.assertNotRegex(out, r'1024 SHA256:.*(DSA)')
        self.assertNotRegex(out, r'2048 SHA256:.*(RSA)')

# vi: ts=4 expandtab
