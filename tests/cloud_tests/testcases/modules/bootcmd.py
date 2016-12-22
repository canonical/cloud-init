# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestBootCmd(base.CloudTestCase):
    """Test bootcmd module"""

    def test_bootcmd_host(self):
        """Test boot cmd worked"""
        out = self.get_data_file('hosts')
        self.assertIn('192.168.1.130 us.archive.ubuntu.com', out)

# vi: ts=4 expandtab
