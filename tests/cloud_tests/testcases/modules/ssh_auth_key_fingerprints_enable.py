# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestSshKeyFingerprintsEnable(base.CloudTestCase):
    """Test ssh key fingerprints module."""

    def test_syslog(self):
        """Verify output of syslog."""
        out = self.get_data_file('syslog')
        self.assertRegex(out, r'256 SHA256:.*(ECDSA)')
        self.assertRegex(out, r'256 SHA256:.*(ED25519)')
        self.assertNotRegex(out, r'1024 SHA256:.*(DSA)')
        self.assertNotRegex(out, r'2048 SHA256:.*(RSA)')

# vi: ts=4 expandtab
