# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for testing reporting and event handling."""

import json
import re
from typing import Dict, List, Union

import pytest
import yaml

from tests.integration_tests.instances import IntegrationInstance
from tests.integration_tests.util import (
    ASSETS_DIR,
    verify_clean_boot,
    verify_clean_log,
)

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

REMOVED_MODULES_RE = re.compile(
    r"Module `(?P<module>[\w-]+)` has been removed from cloud-init"
)
SKIPPED_MODULES_RE = re.compile(
    r"Skipping modules '(?P<modules>[\w,-]+)' because "
    r"(?:no applicable config is provided|they are not verified on distro)"
)


def get_skipped_modules(log: str) -> set[str]:
    """Return a set of all skipped modules from cloud-init.log."""
    skipped_modules: set[str] = set()
    for match in REMOVED_MODULES_RE.finditer(log):
        skipped_modules.add(match.groupdict()["module"])
    for match in SKIPPED_MODULES_RE.finditer(log):
        skipped_modules.update(match.groupdict()["modules"].split(","))
    return skipped_modules


def module_name_from_entry(entry: Union[Dict, str, List]) -> str:
    """Return the config module name from a cloud.cfg entry.

    Allowed module config values in /etc/cloud/cloud.cfg are of the form:
    - module-name
    - [ module-name, frequency, arguments ]
    - {"name": "module-name", "freq": PER_ALWAYS, "args": "my args"}
    """
    if isinstance(entry, dict):
        return entry["name"]
    if isinstance(entry, list):
        return entry[0]
    return entry


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
    log = client.read_from_file("/var/log/cloud-init.log")
    skipped_modules = get_skipped_modules(log)
    verify_clean_log(log)
    verify_clean_boot(client)

    server_output = client.read_from_file(
        "/var/tmp/echo_server_output"
    ).splitlines()
    events = [json.loads(line) for line in server_output]
    event_names = [e["name"] for e in events]

    for stage in (
        "init-network",
        "modules-config",
        "modules-final",
    ):
        assert stage in event_names, f"missing webhook event for {stage}"

    # Each config module in the instance's cloud.cfg reported an event in
    # its boot stage. Reading the config from the instance keeps testing
    # independent of the module lists in config/cloud.cfg.tmpl, which vary
    # per distro downstream.
    merged_cfg = yaml.safe_load(client.execute("cloud-init query merged_cfg"))
    stage_modules = {
        "init-network": set(
            map(module_name_from_entry, merged_cfg["cloud_init_modules"])
        ),
        "modules-config": set(
            map(
                module_name_from_entry,
                merged_cfg["cloud_config_modules"],
            )
        ),
        "modules-final": set(
            map(module_name_from_entry, merged_cfg["cloud_final_modules"])
        ),
    }
    for stage, modules in stage_modules.items():
        for module in modules.difference(skipped_modules):
            assert (
                f"{stage}/config-{module}" in event_names
            ), f"no webhook event for module '{module}' in stage {stage}"

    # Assert our datasource activation events exist
    ds_events = [
        e for e in events if e["name"] == "init-network/activate-datasource"
    ]
    assert len(ds_events) == 2  # 1 for start, 1 for stop

    final_events = [e for e in events if e["name"] == "modules-final"]
    assert final_events  # 1 for stop and ignore LP: #1992711 for now
