# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestByobu(base.CloudTestCase):
    """Test Byobu module."""

    def test_byobu_installed(self):
        """Test byobu installed."""
        self.assertPackageInstalled('byobu')

    def test_byobu_profile_enabled(self):
        """Test byobu profile.d file exists."""
        out = self.get_data_file('byobu_profile_enabled')
        self.assertIn('/etc/profile.d/Z97-byobu.sh', out)

    def test_byobu_launch_exists(self):
        """Test byobu-launch exists."""
        out = self.get_data_file('byobu_launch_exists')
        self.assertIn('/usr/bin/byobu-launch', out)

# vi: ts=4 expandtab
