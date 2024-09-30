# This file is part of cloud-init. See LICENSE file for license information.

"""Autoinstall: Support ubuntu live-server autoinstall syntax."""

import logging
import re

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import (
    MetaSchema,
    SchemaProblem,
    SchemaValidationError,
)
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

    if "autoinstall" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'autoinstall' key in configuration",
            name,
        )
        return

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
    validate_config_schema(cfg)
    LOG.debug(
        "Valid autoinstall schema. Config will be processed by %s",
        installer_present,
    )


def validate_config_schema(cfg):
    """Supplemental runtime schema validation for autoinstall yaml.

    Schema validation issues currently result in a warning log currently which
    can be easily ignored because warnings do not bubble up to cloud-init
    status output.

    In the case of the live-installer, we want cloud-init to raise an error
    to set overall cloud-init status to 'error' so it is more discoverable
    in installer environments.

    # TODO(Drop this validation When cloud-init schema is strict and errors)

    :raise: SchemaValidationError if any known schema values are present.
    """
    autoinstall_cfg = cfg["autoinstall"]
    if not isinstance(autoinstall_cfg, dict):
        raise SchemaValidationError(
            [
                SchemaProblem(
                    "autoinstall",
                    "Expected dict type but found:"
                    f" {type(autoinstall_cfg).__name__}",
                )
            ]
        )

    if "version" not in autoinstall_cfg:
        raise SchemaValidationError(
            [SchemaProblem("autoinstall", "Missing required 'version' key")]
        )
    elif not isinstance(autoinstall_cfg.get("version"), int):
        raise SchemaValidationError(
            [
                SchemaProblem(
                    "autoinstall.version",
                    f"Expected int type but found:"
                    f" {type(autoinstall_cfg['version']).__name__}",
                )
            ]
        )
