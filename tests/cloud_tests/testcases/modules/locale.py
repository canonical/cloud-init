# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestLocale(base.CloudTestCase):
    """Test locale is set properly"""

    def test_locale(self):
        """Test locale is set properly"""
        out = self.get_data_file('locale_default')
        self.assertIn('LANG="en_GB.UTF-8"', out)

    def test_locale_a(self):
        """Test locale -a has both options"""
        out = self.get_data_file('locale_a')
        self.assertIn('en_GB.utf8', out)
        self.assertIn('en_US.utf8', out)

    def test_locale_gen(self):
        """Test local.gen file has all entries."""
        out = self.get_data_file('locale_gen')
        self.assertIn('en_GB.UTF-8', out)
        self.assertIn('en_US.UTF-8', out)

# vi: ts=4 expandtab
