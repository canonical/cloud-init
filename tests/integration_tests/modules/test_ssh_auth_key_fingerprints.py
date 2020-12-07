"""Integration test for the ssh_authkey_fingerprints module.

This modules specifies two tests regarding the ``ssh_authkey_fingerprints``
module. The first one verifies that we can disable the module behavior while
the second one verifies if the module is working as expected if enabled.

(This is ported from
``tests/cloud_tests/testcases/modules/ssh_auth_key_fingerprints_disable.yaml``,
``tests/cloud_tests/testcases/modules/ssh_auth_key_fingerprints_enable.yaml``.
)"""
import re

import pytest


USER_DATA_SSH_AUTHKEY_DISABLE = """\
#cloud-config
no_ssh_fingerprints: true
"""

USER_DATA_SSH_AUTHKEY_ENABLE="""\
#cloud-config
ssh_genkeytypes:
  - ecdsa
  - ed25519
ssh_authorized_keys:
  - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDXW9Gg5H7ehjdSc6qDzwNtgCy94XYHhEYlXZMO2+FJrH3wfHGiMfCwOHxcOMt2QiXItULthdeQWS9QjBSSjVRXf6731igFrqPFyS9qBlOQ5D29C4HBXFnQggGVpBNJ82IRJv7szbbe/vpgLBP4kttUza9Dr4e1YM1ln4PRnjfXea6T0m+m1ixNb5432pTXlqYOnNOxSIm1gHgMLxPuDrJvQERDKrSiKSjIdyC9Jd8t2e1tkNLY0stmckVRbhShmcJvlyofHWbc2Ca1mmtP7MlS1VQnfLkvU1IrFwkmaQmaggX6WR6coRJ6XFXdWcq/AI2K6GjSnl1dnnCxE8VCEXBlXgFzad+PMSG4yiL5j8Oo1ZVpkTdgBnw4okGqTYCXyZg6X00As9IBNQfZMFlQXlIo4FiWgj3CO5QHQOyOX6FuEumaU13GnERrSSdp9tCs1Qm3/DG2RSCQBWTfcgMcStIvKqvJ3IjFn0vGLvI3Ampnq9q1SHwmmzAPSdzcMA76HyMUA5VWaBvWHlUxzIM6unxZASnwvuCzpywSEB5J2OF+p6H+cStJwQ32XwmOG8pLp1srlVWpqZI58Du/lzrkPqONphoZx0LDV86w7RUz1ksDzAdcm0tvmNRFMN1a0frDs506oA3aWK0oDk4Nmvk8sXGTYYw3iQSkOvDUUlIsqdaO+w==
"""  # noqa


@pytest.mark.ci
class TestSshAuthkeyFingerprints:

    @pytest.mark.user_data(USER_DATA_SSH_AUTHKEY_DISABLE)
    def test_ssh_authkey_fingerprints_disable(self, client):
        cloudinit_output = client.read_from_file("/var/log/cloud-init.log")
        assert (
            "Skipping module named ssh-authkey-fingerprints, "
            "logging of SSH fingerprints disabled") in cloudinit_output

    @pytest.mark.user_data(USER_DATA_SSH_AUTHKEY_ENABLE)
    def test_ssh_authkey_fingerprints_enable(self, client):
        syslog_output = client.read_from_file("/var/log/syslog")

        assert re.search(r'256 SHA256:.*(ECDSA)', syslog_output) is not None
        assert re.search(r'256 SHA256:.*(ED25519)', syslog_output) is not None
        assert re.search(r'1024 SHA256:.*(DSA)', syslog_output) is None
        assert re.search(r'2048 SHA256:.*(RSA)', syslog_output) is None
