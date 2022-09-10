# Author: Fabian Lichtenegger-Lukas <fabian.lichtenegger-lukas@nts.eu>
# This file is part of cloud-init. See LICENSE file for license information.

"""create-machine-id"""
from logging import Logger

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_ONCE

MODULE_DESCRIPTION = """\
Description that will be used in module documentation.

This will likely take multiple lines.
"""

meta: MetaSchema = {
    "id": "cc_create_machine_id",
    "name": "create-machine-id",
    "title": "Re/creates machine-id",
    "description": MODULE_DESCRIPTION,
    "distros": ["ubuntu"],
    "frequency": PER_ONCE,
    "activate_by_schema_keys": ["create-machine-id"],
    "examples": [
        "create-machine-id: true",
    ],
}

MACHINE_ID_FILES = frozenset(["/etc/machine-id", "/var/lib/dbus/machine-id"])
NL = "\n"

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def supplemental_schema_validation(mid: dict):
    """Validate user-provided machine-id option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param mid: Dict of configuration value under 'machine-id'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    for key, value in sorted(mid.items()):
        if key == "create-machine-id":
            if not isinstance(value, bool):
                errors.append(f"Expected a bool for {key}. Found {value}")

    if errors:
        raise ValueError(
            f"Invalid 'create-machine-id' configuration:{NL}{NL.join(errors)}"
        )


def remove_machine_id(delFiles: frozenset):
    """Removes following files:
      # /etc/machine-id
      # /var/lib/dbus/machine-id

    @raises: OSError
    """
    try:
        for file in delFiles:
            util.del_file(file)
    except OSError as e:
        raise RuntimeError(f"Failed to remove file '{file}'") from e


def create_machine_id():
    """Creates new machine-id with systemd-machine-id-setup

    @raises: ProcessExecutionError
    """
    try:
        subp.subp("systemd-machine-id-setup")
    except subp.ProcessExecutionError as e:
        util.logexc(LOG, f"Could not create machine-id:{NL}{str(e)}")
        raise


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    cmid_section = None

    if "create-machine-id" in cfg:
        LOG.debug("Found create-machine-id section in config")
        cmid_section = util.get_cfg_option_str(cfg, "create-machine-id", False)
    else:
        LOG.debug(
            """Skipping module named %s,
            no 'create-machine-id' configuration found""",
            name,
        )
        return

    # Check if OS uses systemd
    if not subp.which("systemd"):
        LOG.error("systemd is not installed! Won't execute module!")
        return

    supplemental_schema_validation(cmid_section)

    if cmid_section:
        remove_machine_id(MACHINE_ID_FILES)
        create_machine_id()
