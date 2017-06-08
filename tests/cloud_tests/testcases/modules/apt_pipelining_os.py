# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptPipeliningOS(base.CloudTestCase):
    """Test apt-pipelining module."""

    def test_os_pipelining(self):
        """Test pipelining set to os."""
        out = self.get_data_file('90cloud-init-pipelining')
        self.assertIn('Acquire::http::Pipeline-Depth "0";', out)

# vi: ts=4 expandtab
