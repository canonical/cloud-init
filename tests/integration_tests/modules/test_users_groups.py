"""Integration test for the user_groups module.

This test specifies a number of users and groups via user-data, and confirms
that they have been configured correctly in the system under test.
"""
import re

import pytest


USER_DATA = """\
#cloud-config
# Add groups to the system
groups:
  - secret: [root]
  - cloud-users

# Add users to the system. Users are added after groups are added.
users:
  - default
  - name: foobar
    gecos: Foo B. Bar
    primary_group: foobar
    groups: users
    expiredate: 2038-01-19
    lock_passwd: false
    passwd: $6$j212wezy$7H/1LT4f9/N3wpgNunhsIqtMj62OKiS3nyNwuizouQc3u7MbYCarYe\
AHWYPYb2FT.lbioDm2RrkJPb9BZMN1O/
  - name: barfoo
    gecos: Bar B. Foo
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: [cloud-users, secret]
    lock_passwd: true
  - name: cloudy
    gecos: Magic Cloud App Daemon User
    inactive: true
    system: true
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestUsersGroups:
    @pytest.mark.parametrize(
        "getent_args,regex",
        [
            # Test the ubuntu group
            (["group", "ubuntu"], r"ubuntu:x:[0-9]{4}:"),
            # Test the cloud-users group
            (["group", "cloud-users"], r"cloud-users:x:[0-9]{4}:barfoo"),
            # Test the ubuntu user
            (
                ["passwd", "ubuntu"],
                r"ubuntu:x:[0-9]{4}:[0-9]{4}:Ubuntu:/home/ubuntu:/bin/bash",
            ),
            # Test the foobar user
            (
                ["passwd", "foobar"],
                r"foobar:x:[0-9]{4}:[0-9]{4}:Foo B. Bar:/home/foobar:",
            ),
            # Test the barfoo user
            (
                ["passwd", "barfoo"],
                r"barfoo:x:[0-9]{4}:[0-9]{4}:Bar B. Foo:/home/barfoo:",
            ),
            # Test the cloudy user
            (["passwd", "cloudy"], r"cloudy:x:[0-9]{3,4}:"),
        ],
    )
    def test_users_groups(self, regex, getent_args, class_client):
        """Use getent to interrogate the various expected outcomes"""
        result = class_client.execute(["getent"] + getent_args)
        assert re.search(regex, result.stdout) is not None, (
            "'getent {}' resulted in '{}', "
            "but expected to match regex {}".format(
                ' '.join(getent_args), result.stdout, regex))

    def test_user_root_in_secret(self, class_client):
        """Test root user is in 'secret' group."""
        output = class_client.execute("groups root").stdout
        _, groups_str = output.split(":", maxsplit=1)
        groups = groups_str.split()
        assert "secret" in groups
