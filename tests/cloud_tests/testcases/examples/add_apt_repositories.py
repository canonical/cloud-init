# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestAptconfigurePrimary(base.CloudTestCase):
    """Example cloud-config test"""

    def test_ubuntu_sources(self):
        """Test no default Ubuntu entries exist"""
        out = self.get_data_file('ubuntu.sources.list')
        self.assertEqual(0, int(out))

    def test_gatech_sources(self):
        """Test GaTech entires exist"""
        out = self.get_data_file('gatech.sources.list')
        self.assertEqual(20, int(out))

# vi: ts=4 expandtab
