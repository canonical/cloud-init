import re

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
drivers:
    nvidia:
        license-accepted: true
"""

# NOTE(VM.GPU2.1 is not in all availability_domains: use qIZq:US-ASHBURN-AD-1)


@pytest.mark.adhoc  # Expensive instance type
@pytest.mark.skipif(PLATFORM != "oci", reason="Test is OCI specific")
def test_ubuntu_drivers_installed(session_cloud: IntegrationCloud):
    with session_cloud.launch(
        launch_kwargs={"instance_type": "VM.GPU2.1"}, user_data=USER_DATA
    ) as client:
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert 1 == log.count(
            "Installing and activating NVIDIA drivers "
            "(nvidia/license-accepted=True, version=latest)"
        )
        result = client.execute("dpkg -l | grep nvidia")
        assert result.ok, "No nvidia packages found"
        assert re.search(
            r"ii\s+linux-modules-nvidia-\d+-server", result.stdout
        ), (
            f"Did not find specific nvidia drivers packages in:"
            f" {result.stdout}"
        )
