# This file is part of cloud-init. See LICENSE file for license information.

"""Autoinstall: Support ubuntu live-server autoinstall syntax."""

import re
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import (
    MetaSchema,
    SchemaProblem,
    SchemaValidationError,
    get_meta_doc,
)
from cloudinit.settings import PER_ONCE
from cloudinit.subp import subp

LOG = logging.getLogger(__name__)

distros = ["ubuntu"]

meta: MetaSchema = {
    "id": "cc_ubuntu_autoinstall",
    "name": "Ubuntu Autoinstall",
    "title": "Support Ubuntu live-server install syntax",
    "description": dedent(
        """\
        Ubuntu's autoinstall YAML supports single-system automated installs
        in either the live-server install, via the ``subiquity`` snap, or the
        next generation desktop installer, via `ubuntu-desktop-install` snap.
        When "autoinstall" directives are provided in either
        ``#cloud-config`` user-data or ``/etc/cloud/cloud.cfg.d`` validate
        minimal autoinstall schema adherance and emit a warning if the
        live-installer is not present.

        The live-installer will use autoinstall directives to seed answers to
        configuration prompts during system install to allow for a
        "touchless" or non-interactive Ubuntu system install.

        For more details on Ubuntu's autoinstaller:
            https://ubuntu.com/server/docs/install/autoinstall
    """
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
            # Tell the live-server installer to provide dhcp6 network config
            # and LVM on a disk matching the serial number prefix CT
            autoinstall:
              version: 1
              network:
                version: 2
                ethernets:
                  enp0s31f6:
                    dhcp6: yes
              storage:
                layout:
                  name: lvm
                  match:
                    serial: CT*
        """
        )
    ],
    "frequency": PER_ONCE,
    "activate_by_schema_keys": ["autoinstall"],
}

__doc__ = get_meta_doc(meta)


LIVE_INSTALLER_SNAPS = ("subiquity", "ubuntu-desktop-installer")


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:

    if "autoinstall" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'autoinstall' key in configuration",
            name,
        )
        return

    snap_list, _ = subp(["snap", "list"])
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
