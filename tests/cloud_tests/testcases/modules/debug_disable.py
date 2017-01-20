# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestDebugDisable(base.CloudTestCase):
    """Disable debug messages"""

    def test_debug_disable(self):
        """Test verbose output missing from logs"""
        out = self.get_data_file('cloud-init.log')
        self.assertNotIn(
            out, r'Skipping module named [a-z].* verbose printing disabled')

# vi: ts=4 expandtab
