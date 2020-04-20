# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestPassword(base.CloudTestCase):
    """Test password module."""

    # TODO add test to make sure password is actually "password"

    def test_shadow(self):
        """Test ubuntu user in shadow."""
        out = self.get_data_file('shadow')
        self.assertIn('ubuntu:', out)

    def test_sshd_config(self):
        """Test sshd config allows passwords."""
        out = self.get_data_file('sshd_config')
        self.assertIn('PasswordAuthentication yes', out)

# vi: ts=4 expandtab
