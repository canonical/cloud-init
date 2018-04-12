# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestNtpChrony(base.CloudTestCase):
    """Test ntp module with chrony client"""

    def test_chrony_entires(self):
        """Test chrony config entries"""
        out = self.get_data_file('chrony_conf')
        self.assertIn('.pool.ntp.org', out)

# vi: ts=4 expandtab
