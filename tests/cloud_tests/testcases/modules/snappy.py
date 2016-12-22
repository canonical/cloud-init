# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestSnappy(base.CloudTestCase):
    """Test snappy module"""

    def test_snappy_version(self):
        """Test snappy version output"""
        out = self.get_data_file('snap_version')
        self.assertIn('snap ', out)
        self.assertIn('snapd ', out)
        self.assertIn('series ', out)
        self.assertIn('ubuntu ', out)

# vi: ts=4 expandtab
