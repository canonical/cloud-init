# This file is part of cloud-init. See LICENSE file for license information.

"""Autoinstall: Support ubuntu live-server autoinstall syntax."""

import logging
import re

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_ONCE

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_ubuntu_autoinstall",
    "distros": ["ubuntu"],
    "frequency": PER_ONCE,
    "activate_by_schema_keys": ["autoinstall"],
}


LIVE_INSTALLER_SNAPS = ("subiquity", "ubuntu-desktop-installer")


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:

    util.wait_for_snap_seeded(cloud)
    snap_list, _ = subp.subp(["snap", "list"])
    installer_present = None
    for snap_name in LIVE_INSTALLER_SNAPS:
        if re.search(snap_name, snap_list):
            installer_present = snap_name
    if not installer_present:
        LOG.warning(
            "Skipping autoinstall module. Expected one of the Ubuntu"
            " installer snap packages to be present: %s",
            ", ".join(LIVE_INSTALLER_SNAPS),
        )
        return
    LOG.debug(
        "Valid autoinstall schema. Config will be processed by %s",
        installer_present,
    )
