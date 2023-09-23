"""Integration test for the ssh module.

This module has two tests to verify if we can create ssh keys
through the ``ssh`` module. The first test asserts that some keys
were not created while the second one verifies if the expected
keys were created.

(This is ported from
``tests/cloud_tests/testcases/modules/ssh_keys_generate.yaml``.)"""

import pytest

USER_DATA = """\
#cloud-config
ssh_genkeytypes:
  - ecdsa
  - ed25519
authkey_hash: sha512
"""


@pytest.mark.ci
@pytest.mark.user_data(USER_DATA)
class TestSshKeysGenerate:
    @pytest.mark.parametrize(
        "ssh_key_path",
        (
            "/etc/ssh/ssh_host_rsa_key.pub",
            "/etc/ssh/ssh_host_rsa_key",
        ),
    )
    def test_ssh_keys_not_generated(self, ssh_key_path, class_client):
        out = class_client.execute("test -e {}".format(ssh_key_path))
        assert out.failed

    @pytest.mark.parametrize(
        "ssh_key_path",
        (
            "/etc/ssh/ssh_host_ecdsa_key.pub",
            "/etc/ssh/ssh_host_ecdsa_key",
            "/etc/ssh/ssh_host_ed25519_key.pub",
            "/etc/ssh/ssh_host_ed25519_key",
        ),
    )
    def test_ssh_keys_generated(self, ssh_key_path, class_client):
        out = class_client.read_from_file(ssh_key_path)
        assert "" != out.strip()
