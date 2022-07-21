import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import get_inactive_modules, verify_clean_log


@pytest.mark.ci
def test_active_modules(client: IntegrationInstance):
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log, ignore_deprecations=False)
    assert {"snap"} == get_inactive_modules(log)
