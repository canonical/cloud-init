# Copyright (C) 2024, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.net.netplan import CLOUDINIT_NETPLAN_FILE
from cloudinit.settings import PER_INSTANCE
import logging
import os
import re

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_netplan_nm_patch",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}


def exec_cmd(command: str) -> str | None:
    try:
        result = subp.subp(command)
        if result.stdout is not None:
            return result.stdout
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to execute command: %s", e)
        return None
    LOG.debug("Command has no stdout: %s", command)
    return None


def get_netplan_generated_configs() -> list[str]:
    """Get the UUIDs of all connections starting with 'netplan-'."""
    output = exec_cmd(["nmcli", "connection", "show"])
    if output is None:
        return []

    netplan_conns = []
    for line in output.splitlines():
        if line.startswith("netplan-"):
            parts = line.split()
            if len(parts) > 1:
                # name = parts[0]
                uuid = parts[1]
                netplan_conns.append(uuid)
    return netplan_conns


def get_connection_object_path(uuid: str) -> str | None:
    """Get the D-Bus object path for a connection by UUID."""
    output = exec_cmd(
        [
            "busctl",
            "call",
            "org.freedesktop.NetworkManager",
            "/org/freedesktop/NetworkManager/Settings",
            "org.freedesktop.NetworkManager.Settings",
            "GetConnectionByUuid",
            "s",
            uuid,
        ]
    )

    path_match = (
        re.search(
            r'o\s+"(/org/freedesktop/NetworkManager/Settings/\d+)"', output
        )
        if output
        else None
    )
    if path_match:
        return path_match.group(1)
    else:
        LOG.error("Failed to find object path for connection: %s", uuid)
        return None


def save_connection(obj_path: str) -> None:
    """Call the Save method on the D-Bus obj path for a connection."""
    result = exec_cmd(
        [
            "busctl",
            "call",
            "org.freedesktop.NetworkManager",
            obj_path,
            "org.freedesktop.NetworkManager.Settings.Connection",
            "Save",
        ]
    )

    if result is None:
        LOG.error("Failed to save connection: %s", obj_path)
    else:
        LOG.debug("Saved connection: %s", obj_path)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    LOG.debug("Applying netplan patch")

    # remove cloud-init file after NetworkManager has generated
    # replacement netplan configurations to avoid conflicts in the
    # future

    try:
        np_conns = get_netplan_generated_configs()
        if not np_conns:
            LOG.debug("No netplan connections found")
            return

        for conn_uuid in np_conns:
            obj_path = get_connection_object_path(conn_uuid)
            if obj_path is None:
                continue
            save_connection(obj_path)

        os.remove(CLOUDINIT_NETPLAN_FILE)
        LOG.debug("Netplan cfg has been patched: %s", CLOUDINIT_NETPLAN_FILE)
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to patch netplan cfg: %s", e)
    except Exception as e:
        LOG.error("Failed to patch netplan cfg: %s", e)
