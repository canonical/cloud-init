# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSSHKeys(base.CloudTestCase):
    """Example cloud-config test"""

    def test_cert_count(self):
        """Test cert count"""
        out = self.get_data_file('cert_count')
        self.assertEqual(20, int(out))

    def test_dsa_public(self):
        """Test DSA key has ending"""
        out = self.get_data_file('dsa_public')
        self.assertIn('ZN4XnifuO5krqAybngIy66PMEoQ= smoser@localhost', out)

    def test_rsa_public(self):
        """Test RSA key has specific ending"""
        out = self.get_data_file('rsa_public')
        self.assertIn('PemAWthxHO18QJvWPocKJtlsDNi3 smoser@localhost', out)

    def test_auth_keys(self):
        """Test authorized keys has specific ending"""
        out = self.get_data_file('auth_keys')
        self.assertIn('QPOt5Q8zWd9qG7PBl9+eiH5qV7NZ mykey@host', out)
        self.assertIn('Hj29SCmXp5Kt5/82cD/VN3NtHw== smoser@brickies', out)

# vi: ts=4 expandtab
