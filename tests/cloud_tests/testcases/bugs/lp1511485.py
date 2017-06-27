# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestLP1511485(base.CloudTestCase):
    """Test LP# 1511485."""

    def test_final_message(self):
        """Test final message exists."""
        out = self.get_data_file('cloud-init-output.log')
        self.assertIn('Final message from cloud-config', out)

# vi: ts=4 expandtab
