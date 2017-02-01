# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestCaCerts(base.CloudTestCase):
    """Test ca certs module"""

    def test_cert_count(self):
        """Test the count is proper"""
        out = self.get_data_file('cert_count')
        self.assertEqual(5, int(out))

    def test_cert_installed(self):
        """Test line from our cert exists"""
        out = self.get_data_file('cert')
        self.assertIn('a36c744454555024e7f82edc420fd2c8', out)

# vi: ts=4 expandtab
