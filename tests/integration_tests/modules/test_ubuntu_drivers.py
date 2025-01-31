import logging
import re

import pytest

from tests.integration_tests.clouds import (
    IntegrationCloud,
    IntegrationInstance,
)
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.util import verify_clean_boot, verify_clean_log

logger = logging.getLogger(__name__)

USER_DATA = """\
#cloud-config
drivers:
    nvidia:
        license-accepted: true
"""


@pytest.mark.skipif(PLATFORM != "oci", reason="Test is OCI specific")
def test_ubuntu_drivers_installed(session_cloud: IntegrationCloud):
    """
    Test the installation of NVIDIA drivers on an OCI instance.

    This test checks that the ubuntu-drivers module installs NVIDIA drivers
    as expected on an OCI instance.

    This test launches its own instance so that it can ensure that a GPU
    instance type is used. The "VM.GPU.A10.1" instance type is used because
    it is the most widely available GPU instance type on OCI.

    Additionally, in case there is limited availability of GPU instances, this
    test launches an instance outside the normal context manager used in other
    tests. This is so that if the instance fails to launch, the test can be
    marked as xfail rather than just failing.

    Test Steps:
    1. Launch a GPU instance with the user data that installs NVIDIA drivers.
    2. Verify that the cloud-init log is clean.
    3. Verify that the instance boots cleanly.
    4. Verify that the NVIDIA drivers are installed as expected.
    """
    try:
        client = session_cloud.launch(
            launch_kwargs={"instance_type": "VM.GPU.A10.1"},
            user_data=USER_DATA,
        )
    except Exception as e:
        pytest.xfail(f"Instance launch failed: {e}")

    try:
        _do_test(client)
    finally:
        client.destroy()


def _do_test(client: IntegrationInstance):
    """Performs above test steps on the given client."""
    log = client.read_from_file("/var/log/cloud-init.log")
    verify_clean_log(log)
    verify_clean_boot(client)
    assert 1 == log.count(
        "Installing and activating NVIDIA drivers "
        "(nvidia/license-accepted=True, version=latest)"
    )
    result = client.execute("dpkg -l | grep nvidia")
    assert result.ok, "No nvidia packages found"
    assert re.search(
        r"ii\s+nvidia.*-\d+-server", result.stdout
    ), f"Did not find specific nvidia driver packages in: {result.stdout}"
