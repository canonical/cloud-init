"""Integration tests for CLI functionality

These would be for behavior manually invoked by user from the command line
"""

import pytest

from tests.integration_tests.instances import IntegrationInstance

VALID_USER_DATA = """\
#cloud-config
runcmd:
  - echo 'hi' > /var/tmp/test
"""

INVALID_USER_DATA_HEADER = """\
runcmd:
  - echo 'hi' > /var/tmp/test
"""

INVALID_USER_DATA_SCHEMA = """\
#cloud-config
updates:
 notnetwork: -1
apt_pipelining: bogus
"""


@pytest.mark.user_data(VALID_USER_DATA)
def test_valid_userdata(client: IntegrationInstance):
    """Test `cloud-init schema` with valid userdata.

    PR #575
    """
    result = client.execute("cloud-init schema --system")
    assert result.ok
    assert "Valid cloud-config: system userdata" == result.stdout.strip()
    result = client.execute("cloud-init status --long")
    if not result.ok:
        raise AssertionError(
            f"Unexpected error from cloud-init status: {result}"
        )


@pytest.mark.user_data(INVALID_USER_DATA_HEADER)
def test_invalid_userdata(client: IntegrationInstance):
    """Test `cloud-init schema` with invalid userdata.

    PR #575
    """
    result = client.execute("cloud-init schema --system")
    assert not result.ok
    assert "Cloud config schema errors" in result.stderr
    assert 'needs to begin with "#cloud-config"' in result.stderr
    result = client.execute("cloud-init status --long")
    if not result.ok:
        raise AssertionError(
            f"Unexpected error from cloud-init status: {result}"
        )


@pytest.mark.user_data(INVALID_USER_DATA_SCHEMA)
def test_invalid_userdata_schema(client: IntegrationInstance):
    """Test invalid schema represented as Warnings, not fatal

    PR #1175
    """
    result = client.execute("cloud-init status --long")
    assert result.ok
    log = client.read_from_file("/var/log/cloud-init.log")
    warning = (
        "[WARNING]: Invalid cloud-config provided:\napt_pipelining: 'bogus'"
        " is not valid under any of the given schemas\nupdates: Additional"
        " properties are not allowed ('notnetwork' was unexpected)"
    )
    assert warning in log
    result = client.execute("cloud-init status --long")
    if not result.ok:
        raise AssertionError(
            f"Unexpected error from cloud-init status: {result}"
        )
