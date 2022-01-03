"""Test installation configuration of puppet module."""
import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_log

SERVICE_DATA = """\
#cloud-config
puppet:
  install: true
  install_type: packages
"""


@pytest.mark.user_data(SERVICE_DATA)
def test_puppet_service(client: IntegrationInstance):
    """Basic test that puppet gets installed and runs."""
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    assert client.execute("systemctl is-active puppet").ok
    assert "Running command ['puppet', 'agent'" not in log


EXEC_DATA = """\
#cloud-config
puppet:
  install: true
  install_type: packages
  exec: true
  exec_args: ['--noop']
"""


@pytest.mark.user_data
@pytest.mark.user_data(EXEC_DATA)
def test_pupet_exec(client: IntegrationInstance):
    """Basic test that puppet gets installed and runs."""
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Running command ['puppet', 'agent', '--noop']" in log
