"""Integration tests for CLI functionality

These would be for behavior manually invoked by user from the command line
"""

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM

VALID_USER_DATA = """\
#cloud-config
runcmd:
  - echo 'hi' > /var/tmp/test
"""

INVALID_USER_DATA_HEADER = """\
runcmd:
  - echo 'hi' > /var/tmp/test
"""

# The '-' in 'hashed-password' fails schema validation
INVALID_USER_DATA_SCHEMA = """\
#cloud-config
users:
  - default
  - name: newsuper
    gecos: Big Stuff
    groups: users, admin
    sudo: ALL=(ALL) NOPASSWD:ALL
    hashed-password: asdfasdf
    shell: /bin/bash
    lock_passwd: true
"""


@pytest.mark.user_data(VALID_USER_DATA)
def test_valid_userdata(client: IntegrationInstance):
    """Test `cloud-init schema` with valid userdata.

    PR #575
    """
    result = client.execute("cloud-init schema --system")
    assert result.ok
    assert "Valid schema user-data" in result.stdout.strip()
    result = client.execute("cloud-init status --long")
    if not result.ok:
        raise AssertionError(
            f"Unexpected error from cloud-init status: {result}"
        )


@pytest.mark.skipif(
    PLATFORM == "qemu", reason="QEMU only supports #cloud-config userdata"
)
@pytest.mark.user_data(INVALID_USER_DATA_HEADER)
def test_invalid_userdata(client: IntegrationInstance):
    """Test `cloud-init schema` with invalid userdata.

    PR #575
    """
    result = client.execute("cloud-init schema --system")
    assert not result.ok
    assert "Cloud config schema errors" in result.stderr
    assert (
        "Expected first line to be one of: #!, ## template: jinja,"
        " #cloud-boothook, #cloud-config" in result.stderr
    )
    result = client.execute("cloud-init status --long")
    assert (
        2 == result.return_code
    ), f"Unexpected exit code {result.return_code}"


@pytest.mark.user_data(INVALID_USER_DATA_SCHEMA)
def test_invalid_userdata_schema(client: IntegrationInstance):
    """Test invalid schema represented as Warnings, not fatal

    PR #1175
    """
    result = client.execute("cloud-init status --long")
    assert (
        2 == result.return_code
    ), f"Unexpected exit code {result.return_code}"
    log = client.read_from_file("/var/log/cloud-init.log")
    warning = (
        "[WARNING]: Invalid cloud-config provided: Please run "
        "'sudo cloud-init schema --system' to see the schema errors."
    )
    assert warning in log
    assert "asdfasdf" not in log
