# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestLxdBridge(base.CloudTestCase):
    """Test LXD module."""

    def test_lxd(self):
        """Test lxd installed."""
        out = self.get_data_file('lxd')
        self.assertIn('/usr/bin/lxd', out)

    def test_lxc(self):
        """Test lxc installed."""
        out = self.get_data_file('lxc')
        self.assertIn('/usr/bin/lxc', out)

    def test_bridge(self):
        """Test bridge config."""
        out = self.get_data_file('lxc-bridge')
        self.assertIn('lxdbr0', out)
        self.assertIn('10.100.100.1/24', out)

# vi: ts=4 expandtab
