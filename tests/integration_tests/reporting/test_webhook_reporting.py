# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for testing reporting and event handling."""

import json

import pytest

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import ASSETS_DIR, verify_clean_log

URL = "http://127.0.0.1:55555"

USER_DATA = f"""\
#cloud-config
reporting:
  webserver:
    type: webhook
    endpoint: "{URL}"
    timeout: 1
    retries: 1

"""


@pytest.mark.user_data(USER_DATA)
def test_webhook_reporting(client: IntegrationInstance):
    """Test when using webhook reporting that we get expected events.

    This test setups a simple echo server that prints out POST data out to
    a file. Ensure that that file contains all of the expected events.
    """
    client.push_file(ASSETS_DIR / "echo_server.py", "/var/tmp/echo_server.py")
    client.push_file(
        ASSETS_DIR / "echo_server.service",
        "/etc/systemd/system/echo_server.service",
    )
    client.execute("cloud-init clean --logs")
    client.execute("systemctl start echo_server.service")
    # Run through our standard process here. This remove any uncertainty
    # around messages transmitting during pre-network boot.
    client.execute(
        "cloud-init init --local; "
        "cloud-init init; "
        "cloud-init modules --mode=config; "
        "cloud-init modules --mode=final; "
        "cloud-init status --wait"
    )
    verify_clean_log(client.read_from_file("/var/log/cloud-init.log"))

    server_output = client.read_from_file(
        "/var/tmp/echo_server_output"
    ).splitlines()
    events = [json.loads(line) for line in server_output]

    # Only time this should be less is if we remove modules
    assert len(events) > 54, events

    # Assert our first and last expected messages exist
    ds_events = [
        e for e in events if e["name"] == "init-network/activate-datasource"
    ]
    assert len(ds_events) == 2  # 1 for start, 1 for stop

    final_events = [e for e in events if e["name"] == "modules-final"]
    assert final_events  # 1 for stop and ignore LP: #1992711 for now
