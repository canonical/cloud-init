# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestNtp(base.CloudTestCase):
    """Test ntp module"""

    def test_ntp_installed(self):
        """Test ntp installed"""
        self.assertPackageInstalled('ntp')

    def test_ntp_dist_entries(self):
        """Test dist config file is empty"""
        out = self.get_data_file('ntp_conf_dist_empty')
        self.assertEqual(0, int(out))

    def test_ntp_entries(self):
        """Test config entries"""
        out = self.get_data_file('ntp_conf_pool_list')
        self.assertIn('pool.ntp.org iburst', out)

# vi: ts=4 expandtab
