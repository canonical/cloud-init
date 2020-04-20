# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestUpgrade(base.CloudTestCase):
    """Example cloud-config test."""

    def test_upgrade(self):
        """Test upgrade exists in apt history."""
        out = self.get_data_file('cloud-init.log')
        self.assertIn(
            '[CLOUDINIT] util.py[DEBUG]: apt-upgrade '
            '[eatmydata apt-get --option=Dpkg::Options::=--force-confold '
            '--option=Dpkg::options::=--force-unsafe-io --assume-yes --quiet '
            'dist-upgrade] took', out)

# vi: ts=4 expandtab
