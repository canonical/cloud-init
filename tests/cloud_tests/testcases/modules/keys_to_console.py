# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestKeysToConsole(base.CloudTestCase):
    """Test proper keys are included and excluded to console"""

    def test_excluded_keys(self):
        """Test excluded keys missing"""
        out = self.get_data_file('syslog')
        self.assertNotIn('DSA', out)
        self.assertNotIn('ECDSA', out)

    def test_expected_keys(self):
        """Test expected keys exist"""
        out = self.get_data_file('syslog')
        self.assertIn('ED25519', out)
        self.assertIn('RSA', out)

# vi: ts=4 expandtab
