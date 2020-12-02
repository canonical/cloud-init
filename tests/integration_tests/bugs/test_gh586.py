"""Integration test for pull #586

If a non-default AuthorizedKeysFile is specified in /etc/ssh/sshd_config,
ensure we can still ssh as expected.
"""
import paramiko
import pytest
from io import StringIO
from tests.integration_tests.assets import get_test_keypair


public_key, private_key = get_test_keypair()
USER_DATA = """\
#cloud-config
bootcmd:
  - sed -i 's/#AuthorizedKeysFile.*/AuthorizedKeysFile\\ .ssh\\/authorized_keys2/' /etc/ssh/sshd_config
ssh_authorized_keys:
 - {public_key}
""".format(public_key=public_key)  # noqa: E501


@pytest.mark.sru_2020_11
@pytest.mark.user_data(USER_DATA)
def test_non_default_authorized_keys(client):
    sshd = client.read_from_file('/etc/ssh/sshd_config')
    assert 'AuthorizedKeysFile .ssh/authorized_keys2' in sshd

    ssh_dir = client.execute('ls /home/ubuntu/.ssh').stdout
    assert 'authorized_keys2' in ssh_dir

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    paramiko_key = paramiko.RSAKey.from_private_key(StringIO(private_key))

    # Will fail with paramiko.ssh_exception.AuthenticationException
    # if this bug isn't fixed
    ssh.connect(client.instance.ip, username='ubuntu', pkey=paramiko_key)
