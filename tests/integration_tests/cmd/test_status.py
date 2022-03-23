"""Tests for `cloud-init status`"""
from time import sleep

import pytest

from tests.integration_tests.clouds import ImageSpecification, IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance


# We're implementing our own here in case cloud-init status --wait
# isn't working correctly (LP: #1966085)
def _wait_for_cloud_init(client: IntegrationInstance):
    last_exception = None
    for _ in range(30):
        try:
            result = client.execute("cloud-init status")
            if result and result.ok:
                return result
        except Exception as e:
            last_exception = e
        sleep(1)
    raise Exception(
        "cloud-init status did not return successfully."
    ) from last_exception


def _remove_nocloud_dir_and_reboot(client: IntegrationInstance):
    client.execute("rm -rf /var/lib/cloud/seed/nocloud-net")
    client.execute("cloud-init clean --logs --reboot")


@pytest.mark.ubuntu
@pytest.mark.lxd_container
def test_wait_when_no_datasource(session_cloud: IntegrationCloud, setup_image):
    """Ensure that when no datasource is found, we get status: disabled

    LP: #1966085
    """
    with session_cloud.launch(
        launch_kwargs={
            "config_dict": {"security.devlxd": False},
            "wait": False,
        }
    ) as client:
        # We know this will be an LXD instance due to our pytest mark
        client.instance.execute_via_ssh = False  # type: ignore
        # No ubuntu user if cloud-init didn't run
        client.instance.username = "root"
        # Jammy and above will use LXD datasource by default
        if ImageSpecification.from_os_image().release in [
            "bionic",
            "focal",
            "impish",
        ]:
            _remove_nocloud_dir_and_reboot(client)
        status = _wait_for_cloud_init(client)
        assert status.stdout.strip() == "status: disabled"
        assert client.execute("cloud-init status --wait").ok
