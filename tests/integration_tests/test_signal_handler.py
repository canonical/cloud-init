import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_boot

USER_DATA = """\
#cloud-config
runcmd:
 - pkill cloud-init
"""


@pytest.mark.user_data(USER_DATA)
def test_no_warnings(client: IntegrationInstance):
    """Test that the signal handler does not log errors when suppressed."""
    verify_clean_boot(client)
    log = client.read_from_file("/var/log/cloud-init.log")
    assert "Received signal 15 resulting in exit" in log
