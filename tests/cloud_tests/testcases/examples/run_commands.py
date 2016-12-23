# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script"""
from tests.cloud_tests.testcases import base


class TestRunCmd(base.CloudTestCase):
    """Example cloud-config test"""

    def test_run_cmd(self):
        """Test run command worked"""
        out = self.get_data_file('run_cmd')
        self.assertIn('cloud-init run cmd test', out)

# vi: ts=4 expandtab
