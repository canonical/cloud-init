# This file is part of cloud-init. See LICENSE file for license information.

"""cloud-init Integration Test Verify Script."""
from tests.cloud_tests.testcases import base


class TestUserGroups(base.CloudTestCase):
    """Example cloud-config test."""

    def test_group_ubuntu(self):
        """Test ubuntu group exists."""
        out = self.get_data_file('group_ubuntu')
        self.assertRegex(out, r'ubuntu:x:[0-9]{4}:')

    def test_group_cloud_users(self):
        """Test cloud users group exists."""
        out = self.get_data_file('group_cloud_users')
        self.assertRegex(out, r'cloud-users:x:[0-9]{4}:barfoo')

    def test_user_ubuntu(self):
        """Test ubuntu user exists."""
        out = self.get_data_file('user_ubuntu')
        self.assertRegex(
            out, r'ubuntu:x:[0-9]{4}:[0-9]{4}:Ubuntu:/home/ubuntu:/bin/bash')

    def test_user_foobar(self):
        """Test foobar user exists."""
        out = self.get_data_file('user_foobar')
        self.assertRegex(
            out, r'foobar:x:[0-9]{4}:[0-9]{4}:Foo B. Bar:/home/foobar:')

    def test_user_barfoo(self):
        """Test barfoo user exists."""
        out = self.get_data_file('user_barfoo')
        self.assertRegex(
            out, r'barfoo:x:[0-9]{4}:[0-9]{4}:Bar B. Foo:/home/barfoo:')

    def test_user_cloudy(self):
        """Test cloudy user exists."""
        out = self.get_data_file('user_cloudy')
        self.assertRegex(out, r'cloudy:x:[0-9]{3,4}:')

    def test_user_root_in_secret(self):
        """Test root user is in 'secret' group."""
        _user, _, groups = self.get_data_file('root_groups').partition(":")
        self.assertIn("secret", groups.split(),
                      msg="User root is not in group 'secret'")

# vi: ts=4 expandtab
