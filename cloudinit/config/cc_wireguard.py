# Author: Fabian Lichtenegger-Lukas <fabian.lichtenegger-lukas@nts.eu>
# Author: Josef Tschiggerl <josef.tschiggerl@nts.eu>
# This file is part of cloud-init. See LICENSE file for license information.
"""Wireguard"""

import logging
import re

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_wireguard",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["wireguard"],
}  # type: ignore

LOG = logging.getLogger(__name__)

REQUIRED_WG_INT_KEYS = frozenset(["name", "config_path", "content"])
WG_CONFIG_FILE_MODE = 0o600
NL = "\n"
MIN_KERNEL_VERSION = (5, 6)


def supplemental_schema_validation(wg_int: dict):
    """Validate user-provided wg:interfaces option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    missing = REQUIRED_WG_INT_KEYS.difference(set(wg_int.keys()))
    if missing:
        keys = ", ".join(sorted(missing))
        errors.append(f"Missing required wg:interfaces keys: {keys}")

    for key, value in sorted(wg_int.items()):
        if key == "name" or key == "config_path" or key == "content":
            if not isinstance(value, str):
                errors.append(
                    f"Expected a string for wg:interfaces:{key}. Found {value}"
                )

    if errors:
        raise ValueError(
            f"Invalid wireguard interface configuration:{NL}{NL.join(errors)}"
        )


def write_config(wg_int: dict):
    """Writing user-provided configuration into Wireguard
    interface configuration file.

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: RuntimeError for issues writing of configuration file.
    """
    LOG.debug("Configuring Wireguard interface %s", wg_int["name"])
    try:
        LOG.debug("Writing wireguard config to file %s", wg_int["config_path"])
        util.write_file(
            wg_int["config_path"], wg_int["content"], mode=WG_CONFIG_FILE_MODE
        )
    except Exception as e:
        raise RuntimeError(
            "Failure writing Wireguard configuration file"
            f' {wg_int["config_path"]}:{NL}{str(e)}'
        ) from e


def enable_wg(wg_int: dict, cloud: Cloud):
    """Enable and start Wireguard interface

    @param wg_int: Dict of configuration value under 'wg:interfaces'.

    @raises: RuntimeError for issues enabling WG interface.
    """
    try:
        LOG.debug("Enabling wg-quick@%s at boot", wg_int["name"])
        cloud.distro.manage_service("enable", f'wg-quick@{wg_int["name"]}')
        LOG.debug("Bringing up interface wg-quick@%s", wg_int["name"])
        cloud.distro.manage_service("restart", f'wg-quick@{wg_int["name"]}')
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            f"Failed enabling/starting Wireguard interface(s):{NL}{str(e)}"
        ) from e


def readinessprobe_command_validation(wg_readinessprobes: list):
    """Basic validation of user-provided probes

    @param wg_readinessprobes: List of readinessprobe probe(s).

    @raises: ValueError of wrong datatype provided for probes.
    """
    errors = []
    pos = 0
    for c in wg_readinessprobes:
        if not isinstance(c, str):
            errors.append(
                f"Expected a string for readinessprobe at {pos}. Found {c}"
            )
            pos += 1

    if errors:
        raise ValueError(
            f"Invalid readinessProbe commands:{NL}{NL.join(errors)}"
        )


def readinessprobe(wg_readinessprobes: list):
    """Execute provided readiness probe(s)

    @param wg_readinessprobes: List of readinessprobe probe(s).

    @raises: ProcessExecutionError for issues during execution of probes.
    """
    errors = []
    for c in wg_readinessprobes:
        try:
            LOG.debug("Running readinessprobe: '%s'", str(c))
            subp.subp(c, capture=True, shell=True)
        except subp.ProcessExecutionError as e:
            errors.append(f"{c}: {e}")

    if errors:
        raise RuntimeError(
            f"Failed running readinessprobe command:{NL}{NL.join(errors)}"
        )


def maybe_install_wireguard_packages(cloud: Cloud):
    """Install wireguard packages and tools

    @param cloud: Cloud object

    @raises: Exception for issues during package
    installation.
    """

    packages = ["wireguard-tools"]

    if subp.which("wg"):
        return

    # Install DKMS when Kernel Version lower 5.6
    if util.kernel_version() < MIN_KERNEL_VERSION:
        packages.append("wireguard")

    try:
        cloud.distro.update_package_sources()
    except Exception:
        util.logexc(LOG, "Package update failed")
        raise
    try:
        cloud.distro.install_packages(packages)
    except Exception:
        util.logexc(LOG, "Failed to install wireguard-tools")
        raise


def load_wireguard_kernel_module():
    """Load wireguard kernel module

    @raises: ProcessExecutionError for issues modprobe
    """
    try:
        out = subp.subp("lsmod", capture=True, shell=True)
        if not re.search("wireguard", out.stdout.strip()):
            LOG.debug("Loading wireguard kernel module")
            subp.subp("modprobe wireguard", capture=True, shell=True)
    except subp.ProcessExecutionError as e:
        util.logexc(LOG, f"Could not load wireguard module:{NL}{str(e)}")
        raise


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    wg_section = None

    if "wireguard" in cfg:
        LOG.debug("Found Wireguard section in config")
        wg_section = cfg["wireguard"]
    else:
        LOG.debug(
            "Skipping module named %s, no 'wireguard' configuration found",
            name,
        )
        return

    # install wireguard tools, enable kernel module
    maybe_install_wireguard_packages(cloud)
    load_wireguard_kernel_module()

    for wg_int in wg_section["interfaces"]:
        # check schema
        supplemental_schema_validation(wg_int)

        # write wg config files
        write_config(wg_int)

        # enable wg interfaces
        enable_wg(wg_int, cloud)

    # parse and run readinessprobe parameters
    if (
        "readinessprobe" in wg_section
        and wg_section["readinessprobe"] is not None
    ):
        wg_readinessprobes = wg_section["readinessprobe"]
        readinessprobe_command_validation(wg_readinessprobes)
        readinessprobe(wg_readinessprobes)
    else:
        LOG.debug("Skipping readinessprobe - no checks defined")
