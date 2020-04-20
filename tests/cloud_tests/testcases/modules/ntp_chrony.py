# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
import unittest2

from tests.cloud_tests.testcases import base


class TestNtpChrony(base.CloudTestCase):
    """Test ntp module with chrony client"""

    def setUp(self):
        """Skip this suite of tests on lxd and artful or older."""
        if self.platform == 'lxd':
            if self.is_distro('ubuntu') and self.os_version_cmp('artful') <= 0:
                raise unittest2.SkipTest(
                    'No support for chrony on containers <= artful.'
                    ' LP: #1589780')
        return super(TestNtpChrony, self).setUp()

    def test_chrony_entries(self):
        """Test chrony config entries"""
        out = self.get_data_file('chrony_conf')
        self.assertIn('.pool.ntp.org', out)

# vi: ts=4 expandtab
