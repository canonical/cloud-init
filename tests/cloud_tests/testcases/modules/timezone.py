# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestTimezone(base.CloudTestCase):
    """Test timezone module."""

    def test_timezone(self):
        """Test date prints correct timezone."""
        out = self.get_data_file('timezone')
        self.assertEqual('HDT', out.rstrip())

# vi: ts=4 expandtab
