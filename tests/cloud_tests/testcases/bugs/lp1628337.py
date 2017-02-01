# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestLP1628337(base.CloudTestCase):
    """Test LP# 1511485"""

    def test_fetch_indices(self):
        """Verify no apt errors"""
        out = self.get_data_file('cloud-init-output.log')
        self.assertNotIn('W: Failed to fetch', out)
        self.assertNotIn('W: Some index files failed to download. '
                         'They have been ignored, or old ones used instead.',
                         out)

    def test_ntp(self):
        """Verify can find ntp and install it"""
        out = self.get_data_file('cloud-init-output.log')
        self.assertNotIn('E: Unable to locate package ntp', out)

# vi: ts=4 expandtab
