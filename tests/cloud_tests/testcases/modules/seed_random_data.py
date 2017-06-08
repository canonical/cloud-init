# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestSeedRandom(base.CloudTestCase):
    """Test seed random module."""

    def test_random_seed_data(self):
        """Test random data passed in exists."""
        out = self.get_data_file('seed_data')
        self.assertIn('MYUb34023nD:LFDK10913jk;dfnk:Df', out)

# vi: ts=4 expandtab
