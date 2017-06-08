# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestChefExample(base.CloudTestCase):
    """Test chef module."""

    def test_chef_basic(self):
        """Test chef installed."""
        out = self.get_data_file('chef_installed')
        self.assertIn('install ok', out)

    # FIXME: Add more tests, and/or replace with comprehensive module tests

# vi: ts=4 expandtab
