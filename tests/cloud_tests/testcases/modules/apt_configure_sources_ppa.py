# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestAptconfigureSourcesPPA(base.CloudTestCase):
    """Test apt-configure module."""

    def test_ppa(self):
        """Test specific ppa added."""
        out = self.get_data_file('sources.list')
        self.assertIn(
            'http://ppa.launchpad.net/cloud-init-dev/test-archive/ubuntu', out)

    def test_ppa_key(self):
        """Test ppa key added."""
        out = self.get_data_file('apt-key')
        self.assertIn(
            '1FF0 D853 5EF7 E719 E5C8  1B9C 083D 06FB E4D3 04DF', out)
        self.assertIn('Launchpad PPA for cloud init development team', out)

# vi: ts=4 expandtab
