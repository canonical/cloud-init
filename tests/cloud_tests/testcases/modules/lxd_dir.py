# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestLxdDir(base.CloudTestCase):
    """Test LXD module"""

    def test_lxd(self):
        """Test lxd installed"""
        out = self.get_data_file('lxd')
        self.assertIn('/usr/bin/lxd', out)

    def test_lxc(self):
        """Test lxc installed"""
        out = self.get_data_file('lxc')
        self.assertIn('/usr/bin/lxc', out)

# vi: ts=4 expandtab
