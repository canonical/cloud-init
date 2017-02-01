# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSshKeysGenerate(base.CloudTestCase):
    """Test ssh keys module"""

    # TODO: Check cloud-init-output for the correct keys being generated

    def test_ubuntu_authorized_keys(self):
        """Test passed in key is not in list for ubuntu"""
        out = self.get_data_file('auth_keys_ubuntu')
        self.assertEqual('', out)

    def test_dsa_public(self):
        """Test dsa public key not generated"""
        out = self.get_data_file('dsa_public')
        self.assertEqual('', out)

    def test_dsa_private(self):
        """Test dsa private key not generated"""
        out = self.get_data_file('dsa_private')
        self.assertEqual('', out)

    def test_rsa_public(self):
        """Test rsa public key not generated"""
        out = self.get_data_file('rsa_public')
        self.assertEqual('', out)

    def test_rsa_private(self):
        """Test rsa public key not generated"""
        out = self.get_data_file('rsa_private')
        self.assertEqual('', out)

    def test_ecdsa_public(self):
        """Test ecdsa public key generated"""
        out = self.get_data_file('ecdsa_public')
        self.assertIsNotNone(out)

    def test_ecdsa_private(self):
        """Test ecdsa public key generated"""
        out = self.get_data_file('ecdsa_private')
        self.assertIsNotNone(out)

    def test_ed25519_public(self):
        """Test ed25519 public key generated"""
        out = self.get_data_file('ed25519_public')
        self.assertIsNotNone(out)

    def test_ed25519_private(self):
        """Test ed25519 public key generated"""
        out = self.get_data_file('ed25519_private')
        self.assertIsNotNone(out)

# vi: ts=4 expandtab
