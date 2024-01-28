"""Tests for `cloud-init status`"""
import json

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU, JAMMY
from tests.integration_tests.util import wait_for_cloud_init


def _remove_nocloud_dir_and_reboot(client: IntegrationInstance):
    # On Impish and below, NoCloud will be detected on an LXD container.
    # If we remove this directory, it will no longer be detected.
    client.execute("rm -rf /var/lib/cloud/seed/nocloud-net")
    old_boot_id = client.instance.get_boot_id()
    client.execute("cloud-init clean --logs --reboot")
    client.instance._wait_for_execute(old_boot_id=old_boot_id)


@pytest.mark.skipif(not IS_UBUNTU, reason="Only ever tested on Ubuntu")
@pytest.mark.skipif(
    PLATFORM != "lxd_container",
    reason="Test is LXD specific",
)
def test_wait_when_no_datasource(session_cloud: IntegrationCloud, setup_image):
    """Ensure that when no datasource is found, we get status: disabled

    LP: #1966085
    """
    with session_cloud.launch(
        wait=False,
        launch_kwargs={
            # On Jammy and above, we detect the LXD datasource using a
            # socket available to the container. This prevents the socket
            # from being exposed in the container, causing datasource detection
            # to fail. ds-identify will then have failed to detect a datasource
            "config_dict": {"security.devlxd": False},
        },
    ) as client:
        # We know this will be an LXD instance due to our pytest mark
        client.instance.execute_via_ssh = False  # pyright: ignore
        # No ubuntu user if cloud-init didn't run
        client.instance.username = "root"
        # Jammy and above will use LXD datasource by default
        if CURRENT_RELEASE < JAMMY:
            _remove_nocloud_dir_and_reboot(client)
        status_out = wait_for_cloud_init(client).stdout.strip()
        assert "status: disabled" in status_out
        assert client.execute("cloud-init status --wait").ok


USER_DATA = """\
#cloud-config
ca-certs:
  remove_defaults: false
  invalid_key: true
"""


@pytest.mark.user_data(USER_DATA)
def test_status_json_errors(client):
    """Ensure that deprecated logs end up in the recoverable errors and that
    machine readable status contains recoverable errors
    """
    status_json = client.execute("cat /run/cloud-init/status.json").stdout
    assert json.loads(status_json)["v1"]["init"]["recoverable_errors"].get(
        "DEPRECATED"
    )

    status_json = client.execute("cloud-init status --format json").stdout
    assert "Deprecated cloud-config provided:\nca-certs:" in json.loads(
        status_json
    )["init"]["recoverable_errors"].get("DEPRECATED").pop(0)
    assert "Deprecated cloud-config provided:\nca-certs:" in json.loads(
        status_json
    )["recoverable_errors"].get("DEPRECATED").pop(0)
    assert "Invalid cloud-config provided" in json.loads(status_json)["init"][
        "recoverable_errors"
    ].get("WARNING").pop(0)
    assert "Invalid cloud-config provided" in json.loads(status_json)[
        "recoverable_errors"
    ].get("WARNING").pop(0)
