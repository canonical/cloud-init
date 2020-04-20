# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptPipeliningDisable(base.CloudTestCase):
    """Test apt-pipelining module."""

    def test_disable_pipelining(self):
        """Test pipelining disabled."""
        out = self.get_data_file('90cloud-init-pipelining')
        self.assertIn('Acquire::http::Pipeline-Depth "0";', out)

# vi: ts=4 expandtab
