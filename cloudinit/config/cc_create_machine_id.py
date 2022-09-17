# Author: Fabian Lichtenegger-Lukas <fabian.lichtenegger-lukas@nts.eu>
# This file is part of cloud-init. See LICENSE file for license information.

"""create_machine_id"""
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
    "name": "create_machine_id",
    "title": "Re/creates machine-id",
    "description": MODULE_DESCRIPTION,
    "distros": ["ubuntu"],
    "frequency": PER_ONCE,
    "activate_by_schema_keys": ["create_machine_id"],
    "examples": [
        "create_machine_id: true",
    ],
}

MACHINE_ID_FILES = frozenset(["/etc/machine-id", "/var/lib/dbus/machine-id"])
NL = "\n"

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def supplemental_schema_validation(mid: str):
    """Validate user-provided machine-id option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param mid: String

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    if not isinstance(mid, bool):
        errors.append(f"Expected a bool for create_machine_id. Found {mid}")

    if errors:
        raise ValueError(
            f"Invalid 'create_machine_id' configuration:{NL}{NL.join(errors)}"
        )


def remove_machine_id(delFiles: frozenset):
    """Removes following files:
      # /etc/machine-id
      # /var/lib/dbus/machine-id

    @param: frozenset of files to delete

    @raises: Exception
    """
    try:
        for file in delFiles:
            LOG.info("Removing file %s", file)
            util.del_file(file)
    except Exception as e:
        raise RuntimeError(f"Failed to remove file '{file}'") from e


def create_machine_id():
    """Creates new machine-id with systemd-machine-id-setup

    @raises: ProcessExecutionError
    """
    try:
        LOG.info("Creating new machine-id")
        (out, _) = subp.subp("systemd-machine-id-setup")
        LOG.info("%s", out)
    except subp.ProcessExecutionError as e:
        util.logexc(LOG, f"Could not create machine-id:{NL}{str(e)}")
        raise


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    cmid_section = None

    if "create_machine_id" in cfg:
        LOG.debug("Found create_machine_id section in config")
        cmid_section = util.get_cfg_option_str(cfg, "create_machine_id", False)
    else:
        LOG.debug(
            """Skipping module named %s,
            no 'create_machine_id' configuration found""",
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
