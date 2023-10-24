from io import StringIO

import paramiko
import pytest
from paramiko.ssh_exception import SSHException

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU
from tests.integration_tests.util import get_test_rsa_keypair

TEST_USER1_KEYS = get_test_rsa_keypair("test1")
TEST_USER2_KEYS = get_test_rsa_keypair("test2")
TEST_DEFAULT_KEYS = get_test_rsa_keypair("test3")

_USERDATA = """\
#cloud-config
bootcmd:
 - {bootcmd}
ssh_authorized_keys:
 - {default}
users:
- default
- name: test_user1
  ssh_authorized_keys:
    - {user1}
- name: test_user2
  ssh_authorized_keys:
    - {user2}
""".format(
    bootcmd="{bootcmd}",
    default=TEST_DEFAULT_KEYS.public_key,
    user1=TEST_USER1_KEYS.public_key,
    user2=TEST_USER2_KEYS.public_key,
)


def common_verify(client, expected_keys):
    for user, filename, keys in expected_keys:
        # Ensure key is in the key file
        contents = client.read_from_file(filename)
        if user in ["ubuntu", "root"]:
            lines = contents.split("\n")
            if user == "root":
                # Our personal public key gets added by pycloudlib in
                # addition to the default `ssh_authorized_keys`
                assert len(lines) == 2
            else:
                # Clouds will insert the keys we've added to our accounts
                # or for our launches
                assert len(lines) >= 2
            assert keys.public_key.strip() in contents
        else:
            assert contents.strip() == keys.public_key.strip()

        # Ensure we can actually connect
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        paramiko_key = paramiko.RSAKey.from_private_key(
            StringIO(keys.private_key)
        )

        # Will fail with AuthenticationException if
        # we cannot connect
        ssh.connect(
            client.instance.ip,
            username=user,
            pkey=paramiko_key,
            look_for_keys=False,
            allow_agent=False,
        )

        # Ensure other uses can't connect using our key
        other_users = [u[0] for u in expected_keys if u[2] != keys]
        for other_user in other_users:
            with pytest.raises(SSHException):
                print(
                    "trying to connect as {} with key from {}".format(
                        other_user, user
                    )
                )
                ssh.connect(
                    client.instance.ip,
                    username=other_user,
                    pkey=paramiko_key,
                    look_for_keys=False,
                    allow_agent=False,
                )

        # Ensure we haven't messed with any /home permissions
        # See LP: #1940233
        home_dir = "/home/{}".format(user)
        # Home permissions aren't consistent between releases. On ubuntu
        # this can change to 750 once focal is unsupported.
        if CURRENT_RELEASE.series in ("bionic", "focal"):
            home_perms = "755"
        else:
            home_perms = "750"
        if user == "root":
            home_dir = "/root"
            home_perms = "700"
        assert "{} {}".format(user, home_perms) == client.execute(
            'stat -c "%U %a" {}'.format(home_dir)
        )
        if client.execute("test -d {}/.ssh".format(home_dir)).ok:
            assert "{} 700".format(user) == client.execute(
                'stat -c "%U %a" {}/.ssh'.format(home_dir)
            )
        assert "{} 600".format(user) == client.execute(
            'stat -c "%U %a" {}'.format(filename)
        )

        # Also ensure ssh-keygen works as expected
        client.execute("mkdir {}/.ssh".format(home_dir))
        assert client.execute(
            "ssh-keygen -b 2048 -t rsa -f {}/.ssh/id_rsa -q -N ''".format(
                home_dir
            )
        ).ok
        assert client.execute("test -f {}/.ssh/id_rsa".format(home_dir))
        assert client.execute("test -f {}/.ssh/id_rsa.pub".format(home_dir))

    assert "root 755" == client.execute('stat -c "%U %a" /home')


DEFAULT_KEYS_USERDATA = _USERDATA.format(bootcmd='""')


@pytest.mark.skipif(
    not IS_UBUNTU, reason="Tests permissions specific to Ubuntu releases"
)
@pytest.mark.skipif(
    PLATFORM == "qemu",
    reason="QEMU cloud manually adding key interferes with test",
)
@pytest.mark.user_data(DEFAULT_KEYS_USERDATA)
def test_authorized_keys_default(client: IntegrationInstance):
    expected_keys = [
        (
            "test_user1",
            "/home/test_user1/.ssh/authorized_keys",
            TEST_USER1_KEYS,
        ),
        (
            "test_user2",
            "/home/test_user2/.ssh/authorized_keys",
            TEST_USER2_KEYS,
        ),
        ("ubuntu", "/home/ubuntu/.ssh/authorized_keys", TEST_DEFAULT_KEYS),
        ("root", "/root/.ssh/authorized_keys", TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)


AUTHORIZED_KEYS2_USERDATA = _USERDATA.format(
    bootcmd=(
        "sed -i 's;#AuthorizedKeysFile.*;AuthorizedKeysFile "
        "/etc/ssh/authorized_keys %h/.ssh/authorized_keys2;' "
        "/etc/ssh/sshd_config"
    )
)


@pytest.mark.skipif(
    not IS_UBUNTU, reason="Tests permissions specific to Ubuntu releases"
)
@pytest.mark.skipif(
    PLATFORM == "qemu",
    reason="QEMU cloud manually adding key interferes with test",
)
@pytest.mark.user_data(AUTHORIZED_KEYS2_USERDATA)
def test_authorized_keys2(client: IntegrationInstance):
    expected_keys = [
        (
            "test_user1",
            "/home/test_user1/.ssh/authorized_keys2",
            TEST_USER1_KEYS,
        ),
        (
            "test_user2",
            "/home/test_user2/.ssh/authorized_keys2",
            TEST_USER2_KEYS,
        ),
        ("ubuntu", "/home/ubuntu/.ssh/authorized_keys2", TEST_DEFAULT_KEYS),
        ("root", "/root/.ssh/authorized_keys2", TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)


NESTED_KEYS_USERDATA = _USERDATA.format(
    bootcmd=(
        "sed -i 's;#AuthorizedKeysFile.*;AuthorizedKeysFile "
        "/etc/ssh/authorized_keys %h/foo/bar/ssh/keys;' "
        "/etc/ssh/sshd_config"
    )
)


@pytest.mark.skipif(
    not IS_UBUNTU, reason="Tests permissions specific to Ubuntu releases"
)
@pytest.mark.skipif(
    PLATFORM == "qemu",
    reason="QEMU cloud manually adding key interferes with test",
)
@pytest.mark.user_data(NESTED_KEYS_USERDATA)
def test_nested_keys(client: IntegrationInstance):
    expected_keys = [
        ("test_user1", "/home/test_user1/foo/bar/ssh/keys", TEST_USER1_KEYS),
        ("test_user2", "/home/test_user2/foo/bar/ssh/keys", TEST_USER2_KEYS),
        ("ubuntu", "/home/ubuntu/foo/bar/ssh/keys", TEST_DEFAULT_KEYS),
        ("root", "/root/foo/bar/ssh/keys", TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)


EXTERNAL_KEYS_USERDATA = _USERDATA.format(
    bootcmd=(
        "sed -i 's;#AuthorizedKeysFile.*;AuthorizedKeysFile "
        "/etc/ssh/authorized_keys /etc/ssh/authorized_keys/%u/keys;' "
        "/etc/ssh/sshd_config"
    )
)


@pytest.mark.skipif(
    not IS_UBUNTU, reason="Tests permissions specific to Ubuntu releases"
)
@pytest.mark.skipif(
    PLATFORM == "qemu",
    reason="QEMU cloud manually adding key interferes with test",
)
@pytest.mark.user_data(EXTERNAL_KEYS_USERDATA)
def test_external_keys(client: IntegrationInstance):
    expected_keys = [
        (
            "test_user1",
            "/etc/ssh/authorized_keys/test_user1/keys",
            TEST_USER1_KEYS,
        ),
        (
            "test_user2",
            "/etc/ssh/authorized_keys/test_user2/keys",
            TEST_USER2_KEYS,
        ),
        ("ubuntu", "/etc/ssh/authorized_keys/ubuntu/keys", TEST_DEFAULT_KEYS),
        ("root", "/etc/ssh/authorized_keys/root/keys", TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)
