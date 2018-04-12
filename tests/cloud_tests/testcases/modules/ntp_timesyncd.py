# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestNtpTimesyncd(base.CloudTestCase):
    """Test ntp module with systemd-timesyncd client"""

    def test_timesyncd_entries(self):
        """Test timesyncd config entries"""
        out = self.get_data_file('timesyncd_conf')
        self.assertIn('.pool.ntp.org', out)

# vi: ts=4 expandtab
