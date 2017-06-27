# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestDebugEnable(base.CloudTestCase):
    """Test debug messages."""

    def test_debug_enable(self):
        """Test debug messages in cloud-init log."""
        out = self.get_data_file('cloud-init.log')
        self.assertIn('[DEBUG]', out)

# vi: ts=4 expandtab
