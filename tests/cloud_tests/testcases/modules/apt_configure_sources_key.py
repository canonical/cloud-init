# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestAptconfigureSourcesKey(base.CloudTestCase):
    """Test apt-configure module"""

    def test_apt_key_list(self):
        """Test key list updated"""
        out = self.get_data_file('apt_key_list')
        self.assertIn(
            '1FF0 D853 5EF7 E719 E5C8  1B9C 083D 06FB E4D3 04DF', out)
        self.assertIn('Launchpad PPA for cloud init development team', out)

    def test_source_list(self):
        """Test source.list updated"""
        out = self.get_data_file('sources.list')
        self.assertIn(
            'http://ppa.launchpad.net/cloud-init-dev/test-archive/ubuntu', out)

# vi: ts=4 expandtab
