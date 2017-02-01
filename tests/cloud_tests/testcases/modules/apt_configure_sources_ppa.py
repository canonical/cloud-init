# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestAptconfigureSourcesPPA(base.CloudTestCase):
    """Test apt-configure module"""

    def test_ppa(self):
        """test specific ppa added"""
        out = self.get_data_file('sources.list')
        self.assertIn(
            'http://ppa.launchpad.net/curtin-dev/test-archive/ubuntu', out)

    def test_ppa_key(self):
        """test ppa key added"""
        out = self.get_data_file('apt-key')
        self.assertIn(
            '1BC3 0F71 5A3B 8612 47A8  1A5E 55FE 7C8C 0165 013E', out)
        self.assertIn('Launchpad PPA for curtin developers', out)

# vi: ts=4 expandtab
