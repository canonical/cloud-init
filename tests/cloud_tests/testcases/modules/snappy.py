# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSnappy(base.CloudTestCase):
    """Test snappy module"""

    expected_warnings = ('DEPRECATION',)

    def test_snappy_version(self):
        """Test snappy version output"""
        out = self.get_data_file('snapd')
        self.assertIn('Status: install ok installed', out)

# vi: ts=4 expandtab
