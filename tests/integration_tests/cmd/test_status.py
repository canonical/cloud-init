"""Tests for `cloud-init status`"""
import json

import pytest

from tests.integration_tests.clouds import IntegrationCloud
from tests.integration_tests.decorators import retry
from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.integration_settings import PLATFORM
from tests.integration_tests.releases import CURRENT_RELEASE, IS_UBUNTU, JAMMY
from tests.integration_tests.util import (
    push_and_enable_systemd_unit,
    wait_for_cloud_init,
)


def _remove_nocloud_dir_and_reboot(client: IntegrationInstance):
    # On Impish and below, NoCloud will be detected on an LXD container.
    # If we remove this directory, it will no longer be detected.
    client.execute("rm -rf /var/lib/cloud/seed/nocloud-net")
    old_boot_id = client.instance.get_boot_id()
    client.execute("cloud-init clean --logs --reboot")
    client.instance._wait_for_execute(old_boot_id=old_boot_id)


@retry(tries=30, delay=1)
def retry_read_from_file(client: IntegrationInstance, path: str):
    """Retry read_from_file expecting it shortly"""
    return client.read_from_file(path)


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
users:
  - name: something
    ssh-authorized-keys: ["something"]
ca-certs:
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
    assert (
        "Deprecated cloud-config provided: users.0.ssh-authorized-keys"
        in json.loads(status_json)["init"]["recoverable_errors"]
        .get("DEPRECATED")
        .pop(0)
    )
    assert (
        "Deprecated cloud-config provided: users.0.ssh-authorized-keys:"
        in json.loads(status_json)["recoverable_errors"]
        .get("DEPRECATED")
        .pop(0)
    )
    assert "cloud-config failed schema validation" in json.loads(status_json)[
        "init"
    ]["recoverable_errors"].get("WARNING").pop(0)
    assert "cloud-config failed schema validation" in json.loads(status_json)[
        "recoverable_errors"
    ].get("WARNING").pop(0)


EARLY_BOOT_WAIT_USER_DATA = """\
#cloud-config
write_files:
- path: /waitoncloudinit.sh
  permissions: '0755'
  content: |
    #!/bin/sh
    if [ -f /var/lib/cloud/data/status.json ]; then
        MARKER_FILE="/$1.start-hasstatusjson"
    else
        MARKER_FILE="/$1.start-nostatusjson"
    fi
    cloud-init status --wait --long > $1
    date +%s.%N > $MARKER_FILE
"""  # noqa: E501


BEFORE_CLOUD_INIT_LOCAL = """\
[Unit]
Description=BEFORE cloud-init local
DefaultDependencies=no
After=systemd-remount-fs.service
Before=cloud-init-local.service
Before=shutdown.target
Before=sysinit.target
Conflicts=shutdown.target
RequiresMountsFor=/var/lib/cloud

[Service]
Type=simple
ExecStart=/waitoncloudinit.sh /before-local
RemainAfterExit=yes
TimeoutSec=0

# Output needs to appear in instance console output
StandardOutput=journal+console

[Install]
WantedBy=cloud-init.target
"""


@pytest.mark.user_data(EARLY_BOOT_WAIT_USER_DATA)
@pytest.mark.lxd_use_exec
@pytest.mark.skipif(
    PLATFORM not in ("lxd_container", "lxd_vm"),
    reason="Requires use of lxd exec",
)
def test_status_block_through_all_boot_status(client):
    """Assert early boot cloud-init status --wait does not exit early."""
    push_and_enable_systemd_unit(
        client, "before-cloud-init-local.service", BEFORE_CLOUD_INIT_LOCAL
    )
    client.execute("cloud-init clean --logs --reboot")
    wait_for_cloud_init(client).stdout.strip()
    client.execute("cloud-init status --wait")

    # Assert that before-cloud-init-local.service started before
    # cloud-init-local.service could create status.json
    client.execute("test -f /before-local.start-hasstatusjson").failed

    early_unit_timestamp = retry_read_from_file(
        client, "/before-local.start-nostatusjson"
    )
    # Assert the file created at the end of
    # before-cloud-init-local.service is newer than the last log entry in
    # /var/log/cloud-init.log
    events = json.loads(client.execute("cloud-init analyze dump").stdout)
    final_cloud_init_event = events[-1]["timestamp"]
    assert final_cloud_init_event < float(
        early_unit_timestamp
    ), "Systemd unit didn't block on cloud-init status --wait"
