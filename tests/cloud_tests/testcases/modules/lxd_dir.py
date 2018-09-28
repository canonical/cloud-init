# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestLxdDir(base.CloudTestCase):
    """Test LXD module."""

    def setUp(self):
        """Skip on cosmic for two reasons:
        a.) LP: #1795036 - 'lxd init' fails on cosmic kernel.
        b.) apt install lxd installs via snap which can be slow
            as that will download core snap and lxd."""
        if self.os_name == "cosmic":
            raise self.skipTest('Skipping test on cosmic (LP: #1795036).')
        return base.CloudTestCase.setUp(self)

    def test_lxd(self):
        """Test lxd installed."""
        out = self.get_data_file('lxd')
        self.assertIn('/lxd', out)

    def test_lxc(self):
        """Test lxc installed."""
        out = self.get_data_file('lxc')
        self.assertIn('/lxc', out)

# vi: ts=4 expandtab
