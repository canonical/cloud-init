# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestAptconfigureSecurity(base.CloudTestCase):
    """Test apt-configure module"""

    def test_security_mirror(self):
        """Test security lines added and uncommented in source.list"""
        out = self.get_data_file('sources.list')
        self.assertEqual(6, int(out))

# vi: ts=4 expandtab
