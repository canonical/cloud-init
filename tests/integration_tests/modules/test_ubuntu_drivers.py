import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.util import verify_clean_log

USER_DATA = """\
#cloud-config
drivers:
    nvidia:
        license-accepted: true
"""


@pytest.mark.user_data(USER_DATA)
@pytest.mark.oci
def test_ubuntu_drivers_installed(session_cloud: IntegrationCloud):
    with session_cloud.launch(
        launch_kwargs={"instance_type": "VM.GPU3.1"}
    ) as client:
        log = client.read_from_file("/var/log/cloud-init.log")
        verify_clean_log(log)
        assert 1 == log.count(
            "Installing and activating NVIDIA drivers "
            '("nvidia/license-accepted"=True, version=latest)'
        )
        cmd = "apt list --installed | grep -E 'nvidia-*-server'"
        assert client.execute(cmd).ok
