# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestSshKeysProvided(base.CloudTestCase):
    """Test ssh keys module."""

    def test_dsa_public(self):
        """Test dsa public key passed in."""
        out = self.get_data_file('dsa_public')
        self.assertIn('AAAAB3NzaC1kc3MAAACBAPkWy1zbchVIN7qTgM0/yyY8q4RZS8c'
                      'NM4ZpeuE5UB/Nnr6OSU/nmbO8LuM', out)

    def test_dsa_private(self):
        """Test dsa private key passed in."""
        out = self.get_data_file('dsa_private')
        self.assertIn('MIIBuwIBAAKBgQD5Fstc23IVSDe6k4DNP8smPKuEWUvHDTOGaXr'
                      'hOVAfzZ6+jklP', out)

    def test_rsa_public(self):
        """Test rsa public key passed in."""
        out = self.get_data_file('rsa_public')
        self.assertIn('AAAAB3NzaC1yc2EAAAADAQABAAABAQC0/Ho+o3eJISydO2JvIgT'
                      'LnZOtrxPl+fSvJfKDjoOLY0HB2eOjy2s2/2N6d9X9SGZ4', out)

    def test_rsa_private(self):
        """Test rsa public key passed in."""
        out = self.get_data_file('rsa_private')
        self.assertIn('4DOkqNiUGl80Zp1RgZNohHUXlJMtAbrIlAVEk+mTmg7vjfyp2un'
                      'RQvLZpMRdywBm', out)

    def test_ecdsa_public(self):
        """Test ecdsa public key passed in."""
        out = self.get_data_file('ecdsa_public')
        self.assertIn('AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAAB'
                      'BBFsS5Tvky/IC/dXhE/afxxU', out)

    def test_ecdsa_private(self):
        """Test ecdsa public key passed in."""
        out = self.get_data_file('ecdsa_private')
        self.assertIn('AwEHoUQDQgAEWxLlO+TL8gL91eET9p/HFQbqR1A691AkJgZk3jY'
                      '5mpZqxgX4vcgb', out)

    def test_ed25519_public(self):
        """Test ed25519 public key passed in."""
        out = self.get_data_file('ed25519_public')
        self.assertIn('AAAAC3NzaC1lZDI1NTE5AAAAINudAZSu4vjZpVWzId5pXmZg1M6'
                      'G15dqjQ2XkNVOEnb5', out)

    def test_ed25519_private(self):
        """Test ed25519 public key passed in."""
        out = self.get_data_file('ed25519_private')
        self.assertIn('XAAAAAtzc2gtZWQyNTUxOQAAACDbnQGUruL42aVVsyHeaV5mYNT'
                      'OhteXao0Nl5DVThJ2+Q', out)

# vi: ts=4 expandtab
