# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestNtp(base.CloudTestCase):
    """Test ntp module"""

    def test_ntp_installed(self):
        """Test ntp installed"""
        out = self.get_data_file('ntp_installed_empty')
        self.assertEqual(1, int(out))

    def test_ntp_dist_entries(self):
        """Test dist config file has one entry"""
        out = self.get_data_file('ntp_conf_dist_empty')
        self.assertEqual(1, int(out))

    def test_ntp_entires(self):
        """Test config entries"""
        out = self.get_data_file('ntp_conf_empty')
        self.assertIn('pool 0.ubuntu.pool.ntp.org iburst', out)
        self.assertIn('pool 1.ubuntu.pool.ntp.org iburst', out)
        self.assertIn('pool 2.ubuntu.pool.ntp.org iburst', out)
        self.assertIn('pool 3.ubuntu.pool.ntp.org iburst', out)

# vi: ts=4 expandtab
