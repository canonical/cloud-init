# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigureConf(base.CloudTestCase):
    """Test apt-configure module."""

    def test_apt_conf_assumeyes(self):
        """Test config assumes true."""
        out = self.get_data_file('94cloud-init-config')
        self.assertIn('Assume-Yes "true";', out)

    def test_apt_conf_fixbroken(self):
        """Test config fixes broken."""
        out = self.get_data_file('94cloud-init-config')
        self.assertIn('Fix-Broken "true";', out)

# vi: ts=4 expandtab
