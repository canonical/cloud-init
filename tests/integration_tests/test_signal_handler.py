import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import verify_clean_boot

USER_DATA = """\
#cloud-config
runcmd:
 - reboot
"""


@pytest.mark.user_data(USER_DATA)
def test_no_warnings(client: IntegrationInstance):
    """Test that the signal handler does not log errors on reboot.

    Note that for single process boots, `Conflicts=shutdown.target` will
    prevent the shutdown from happening before the cloud-init process has
    exited.
    """
    verify_clean_boot(client)
