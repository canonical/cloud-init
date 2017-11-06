# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestHostname(base.CloudTestCase):
    """Test hostname module."""

    ex_hostname = "cloudinit2"

    def test_hostname(self):
        """Test hostname command shows correct output."""
        out = self.get_data_file('hostname')
        self.assertIn(self.ex_hostname, out)

# vi: ts=4 expandtab
