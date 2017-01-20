# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestPackageInstallUpdateUpgrade(base.CloudTestCase):
    """Test package install update upgrade module"""

    def test_installed_htop(self):
        """Test htop got installed"""
        out = self.get_data_file('dpkg_htop')
        self.assertEqual(1, int(out))

    def test_installed_tree(self):
        """Test tree got installed"""
        out = self.get_data_file('dpkg_tree')
        self.assertEqual(1, int(out))

    def test_apt_history(self):
        """Test apt history for update command"""
        out = self.get_data_file('apt_history_cmdline')
        self.assertIn(
            'Commandline: /usr/bin/apt-get --option=Dpkg::Options'
            '::=--force-confold --option=Dpkg::options::=--force-unsafe-io '
            '--assume-yes --quiet install htop tree', out)

    def test_cloud_init_output(self):
        """Test cloud-init-output for install & upgrade stuff"""
        out = self.get_data_file('cloud-init-output.log')
        self.assertIn('Setting up tree (', out)
        self.assertIn('Setting up htop (', out)
        self.assertIn('Reading package lists...', out)
        self.assertIn('Building dependency tree...', out)
        self.assertIn('Reading state information...', out)
        self.assertIn('Calculating upgrade...', out)

# vi: ts=4 expandtab
