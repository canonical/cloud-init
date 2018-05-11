# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class Test(base.CloudTestCase):
    """Test salt minion module."""

    def test_minon_master(self):
        """Test master value in config."""
        out = self.get_data_file('minion')
        self.assertIn('master: salt.mydomain.com', out)

    def test_minion_pem(self):
        """Test private key."""
        out = self.get_data_file('minion.pem')
        self.assertIn('------BEGIN PRIVATE KEY------', out)
        self.assertIn('<key data>', out)
        self.assertIn('------END PRIVATE KEY-------', out)

    def test_minion_pub(self):
        """Test public key."""
        out = self.get_data_file('minion.pub')
        self.assertIn('------BEGIN PUBLIC KEY-------', out)
        self.assertIn('<key data>', out)
        self.assertIn('------END PUBLIC KEY-------', out)

    def test_grains(self):
        """Test master value in config."""
        out = self.get_data_file('grains')
        self.assertIn('role: web', out)

    def test_minion_installed(self):
        """Test if the salt-minion package is installed"""
        self.assertPackageInstalled('salt-minion')

# vi: ts=4 expandtab
