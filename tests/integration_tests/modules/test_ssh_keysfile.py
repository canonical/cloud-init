import paramiko
import pytest
from io import StringIO
from paramiko.ssh_exception import SSHException

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import get_test_rsa_keypair

TEST_USER1_KEYS = get_test_rsa_keypair('test1')
TEST_USER2_KEYS = get_test_rsa_keypair('test2')
TEST_DEFAULT_KEYS = get_test_rsa_keypair('test3')

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
    bootcmd='{bootcmd}',
    default=TEST_DEFAULT_KEYS.public_key,
    user1=TEST_USER1_KEYS.public_key,
    user2=TEST_USER2_KEYS.public_key,
)
DEFAULT_KEYS_USERDATA = _USERDATA.format(bootcmd='""')
MODIFIED_KEYS_USERDATA = _USERDATA.format(bootcmd=(
    "sed -i 's;#AuthorizedKeysFile.*;AuthorizedKeysFile "
    "/etc/ssh/authorized_keys %h/.ssh/authorized_keys2;' "
    "/etc/ssh/sshd_config"))


def common_verify(client, expected_keys):
    for user, filename, keys in expected_keys:
        contents = client.read_from_file(filename)
        if user in ['ubuntu', 'root']:
            # Our personal public key gets added by pycloudlib
            lines = contents.split('\n')
            assert len(lines) == 2
            assert keys.public_key.strip() in contents
        else:
            assert contents.strip() == keys.public_key.strip()

        # Ensure we can actually connect
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        paramiko_key = paramiko.RSAKey.from_private_key(StringIO(
            keys.private_key))

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
                print('trying to connect as {} with key from {}'.format(
                    other_user, user))
                ssh.connect(
                    client.instance.ip,
                    username=other_user,
                    pkey=paramiko_key,
                    look_for_keys=False,
                    allow_agent=False,
                )

        # Also ensure we haven't messed with any /home permissions
        # See LP: #1940233
        home_dir = '/home/{}'.format(user)
        home_perms = '755'
        if user == 'root':
            home_dir = '/root'
            home_perms = '700'
        assert '{} {}'.format(user, home_perms) == client.execute(
            'stat -c "%U %a" {}'.format(home_dir)
        )
        assert '{} 700'.format(user) == client.execute(
            'stat -c "%U %a" {}/.ssh'.format(home_dir)
        )
        assert '{} 600'.format(user) == client.execute(
            'stat -c "%U %a" {}'.format(filename)
        )
    assert 'root 755' == client.execute('stat -c "%U %a" /home')


@pytest.mark.ubuntu
@pytest.mark.user_data(DEFAULT_KEYS_USERDATA)
def test_authorized_keys_default(client: IntegrationInstance):
    expected_keys = [
        ('test_user1', '/home/test_user1/.ssh/authorized_keys',
         TEST_USER1_KEYS),
        ('test_user2', '/home/test_user2/.ssh/authorized_keys',
         TEST_USER2_KEYS),
        ('ubuntu', '/home/ubuntu/.ssh/authorized_keys',
         TEST_DEFAULT_KEYS),
        ('root', '/root/.ssh/authorized_keys', TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)


@pytest.mark.ubuntu
@pytest.mark.user_data(MODIFIED_KEYS_USERDATA)
def test_authorized_keys_modified(client: IntegrationInstance):
    expected_keys = [
        ('test_user1', '/home/test_user1/.ssh/authorized_keys2',
         TEST_USER1_KEYS),
        ('test_user2', '/home/test_user2/.ssh/authorized_keys2',
         TEST_USER2_KEYS),
        ('ubuntu', '/home/ubuntu/.ssh/authorized_keys2',
         TEST_DEFAULT_KEYS),
        ('root', '/root/.ssh/authorized_keys2', TEST_DEFAULT_KEYS),
    ]
    common_verify(client, expected_keys)
