# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSnap(base.CloudTestCase):
    """Test snap module"""

    def test_snappy_version(self):
        """Expect hello-world and core snaps are installed."""
        out = self.get_data_file('snaplist')
        self.assertIn('core', out)
        self.assertIn('hello-world', out)

# vi: ts=4 expandtab
