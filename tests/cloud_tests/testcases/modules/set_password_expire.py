# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestPasswordExpire(base.CloudTestCase):
    """Test password module."""

    def test_shadow(self):
        """Test user frozen in shadow."""
        out = self.get_data_file('shadow')
        self.assertIn('harry:!:', out)
        self.assertIn('dick:!:', out)
        self.assertIn('tom:!:', out)
        self.assertIn('harry:!:', out)

    def test_sshd_config(self):
        """Test sshd config allows passwords."""
        out = self.get_data_file('sshd_config')
        self.assertIn('PasswordAuthentication yes', out)

# vi: ts=4 expandtab
