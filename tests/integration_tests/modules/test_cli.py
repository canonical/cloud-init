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

INVALID_USER_DATA = """\
runcmd:
  - echo 'hi' > /var/tmp/test
"""


@pytest.mark.sru_2020_11
@pytest.mark.user_data(VALID_USER_DATA)
def test_valid_userdata(client: IntegrationInstance):
    """Test `cloud-init devel schema` with valid userdata.

    PR #575
    """
    result = client.execute('cloud-init devel schema --system')
    assert result.ok
    assert 'Valid cloud-config: system userdata' == result.stdout.strip()


@pytest.mark.sru_2020_11
@pytest.mark.user_data(INVALID_USER_DATA)
def test_invalid_userdata(client: IntegrationInstance):
    """Test `cloud-init devel schema` with invalid userdata.

    PR #575
    """
    result = client.execute('cloud-init devel schema --system')
    assert not result.ok
    assert 'Cloud config schema errors' in result.stderr
    assert 'needs to begin with "#cloud-config"' in result.stderr
