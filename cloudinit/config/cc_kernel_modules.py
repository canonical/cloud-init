# This file is part of cloud-init. See LICENSE file for license information.

"""Kernel Modules"""
import copy
import re
from array import array
from logging import Logger
from textwrap import dedent
from typing import List

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = dedent(
    """\
Manages and enhances kernel modules on a systemd based system.
This module is capable of loading kernel modules at boot as well as
enhance it with parameters.
Beside applying settings during runtime it will also persist all
settings in ``/etc/modules-load.d`` and ``/etc/modprobe.d`.
"""
)

DISTROS = ["debian", "ubuntu"]

meta: MetaSchema = {
    "id": "cc_kernel_modules",
    "name": "Kernel Modules",
    "title": "Manage and enhance kernel modules",
    "description": MODULE_DESCRIPTION,
    "distros": DISTROS,
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["kernel_modules"],
    "examples": [
        dedent(
            """\
    kernel_modules:
      - name: wireguard
        load: true
      - name: v4l2loopback
        load: true
        persist:
          options: "devices=1 video_nr=20 card_label=fakecam exclusive_caps=1"
      - name: zfs
        persist:
          blacklist: true
    """
        ),
    ],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)
NL = "\n"
REQUIRED_KERNEL_MODULES_KEYS = frozenset(["name"])

DEFAULT_CONFIG: dict = {
    "km_cmd": {
        "update": ["update-initramfs", "-u", "-k", "all"],
        "unload": ["rmmod"],
        "is_loaded": ["lsmod"],
    },
    "km_files": {
        "load": {
            "path": "/etc/modules-load.d/50-cloud-init.conf",
            "permissions": 0o600,
        },
        "persist": {
            "path": "/etc/modprobe.d/50-cloud-init.conf",
            "permissions": 0o600,
        },
    },
}


def persist_schema_validation(persist: dict) -> List[str]:
    """Validate user-provided kernel_modules:persist option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param kernel_module: Dictionary.

    @raises: ValueError describing invalid values provided.

    @return list of strings
    """
    errors = []
    for key, value in sorted(persist.items()):
        if key in (
            "alias",
            "install",
            "options",
            "remove",
        ):
            if not isinstance(value, str):
                errors.append(
                    "Expected a string for kernel_modules:"
                    f"persist:{key}. Found {value}."
                )
        elif key == "blacklist":
            if not isinstance(value, bool):
                errors.append(
                    "Expected a boolean for kernel_modules:"
                    f"persist:{key}. Found {value}."
                )
        elif key == "softdep":
            for sdkey, sdvalue in sorted(persist[key].items()):
                if sdkey in ("pre", "post"):
                    if not isinstance(sdvalue, array):
                        errors.append(
                            "Expected an array for kernel_modules:persist:"
                            f"softdep:{sdkey}. Found {sdvalue}."
                        )

    return errors


def supplemental_schema_validation(kernel_module: dict):
    """Validate user-provided kernel_modules option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param kernel_module: Dictionary.

    @raises: ValueError describing invalid values provided.
    """
    errors = []
    missing = REQUIRED_KERNEL_MODULES_KEYS.difference(
        set(kernel_module.keys())
    )
    if missing:
        keys = ", ".join(sorted(missing))
        errors.append(f"Missing required kernel_modules keys: {keys}")

    for key, value in sorted(kernel_module.items()):
        if key == "name":
            if not isinstance(value, str):
                errors.append(
                    "Expected a string for kernel_modules:"
                    f"{key}. Found {value}."
                )
        elif key == "load":
            if not isinstance(value, bool):
                errors.append(
                    "Expected a boolean for kernel_modules:"
                    f"{key}. Found {value}."
                )
        elif key == "persist":
            errors += persist_schema_validation(kernel_module[key])

    if errors:
        raise ValueError(
            f"Invalid kernel_modules configuration:{NL}{NL.join(errors)}"
        )


def prepare_module(module_name: str):
    """Prepare kernel module to be loaded on boot.

    This function appends a kernel module to a file
    (depends on operating system) for loading a module on boot.

    @param module_name: string.

    @raises: RuntimeError when write operation fails.
    """

    LOG.info(
        "Writing %s file for loading kernel modules on boot",
        DEFAULT_CONFIG["km_files"]["load"].get("path"),
    )

    try:
        LOG.debug("Appending kernel module %s", module_name)
        util.write_file(
            DEFAULT_CONFIG["km_files"]["load"]["path"],
            module_name + NL,
            DEFAULT_CONFIG["km_files"]["load"]["permissions"],
            omode="a",
        )
    except Exception as e:
        raise RuntimeError(
            f"Failure appending kernel module '{module_name}' to file "
            f'{DEFAULT_CONFIG["km_files"]["load"]["path"]}:{NL}{str(e)}'
        ) from e


def enhance_module(module_name: str, persist: dict, unload_modules: list):
    """Enhances a kernel modules behavior

    This function appends specific settings and options
    for a kernel module, which will be applied when kernel
    module get's loaded.

    @param module_name: string.
    @param persist: Dictionary
    qparam unload_modules: list

    @raises RuntimeError when write operation fails.
    """

    for (key, value) in persist.items():
        LOG.debug(
            "Enhancing kernel module %s with %s:%s", module_name, key, value
        )
        entry = f"{key} {module_name} {value}"
        # softdep special case
        if key == "softdep":
            entry += " pre:".join({key["pre"]}) + " post: ".join({key["post"]})
        # blacklist special case
        elif key == "blacklist":
            if value:
                unload_modules.append(module_name)
                entry = f"{key} {module_name}"

        try:
            util.write_file(
                DEFAULT_CONFIG["km_files"]["persist"]["path"],
                entry + NL,
                DEFAULT_CONFIG["km_files"]["persist"]["permissions"],
                omode="a",
            )
        except Exception as e:
            raise RuntimeError(
                f"Failure enhancing kernel module '{module_name}':{NL}{str(e)}"
            ) from e


def cleanup():
    """Clean up all kernel specific files

    This function removes all files, which are
    responsible for loading and enhancing kernel modules.

    @raises RuntimeError when remove operation fails
    """

    for action in sorted(DEFAULT_CONFIG["km_files"].keys()):
        file_path = DEFAULT_CONFIG["km_files"][action]["path"]
        LOG.debug("Removing file %s", file_path)
        try:
            util.del_file(file_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not delete file {file_path}:{NL}{str(e)}"
            ) from e


def reload_modules(cloud: Cloud):
    """Reload kernel modules

    This function reload modules in /etc/modules-load.d/cloud-init.conf
    with 'systemd-modules-load' service.

    @raises RuntimeError
    """

    try:
        out = cloud.distro.manage_service("restart", "systemd-modules-load")
        if re.search("Failed", out.stdout.strip()):
            raise Exception(out.stdout.strip())
    except (subp.ProcessExecutionError, Exception) as e:
        raise RuntimeError(
            f"Could not load modules with systemd-modules-load:{NL}{str(e)}"
        ) from e


def is_loaded(module_name: str) -> bool:
    """
    Checks if a kernel module is already loaded

    @param module_name: name of kernel module

    @return bool
    """
    loaded = False
    try:
        out = subp.subp(
            DEFAULT_CONFIG["km_cmd"]["is_loaded"], capture=True, shell=True
        )
        if re.search("^" + module_name, out.stdout.strip()):
            LOG.debug("Kernel module %s is loaded", module_name)
            loaded = True
    except subp.ProcessExecutionError as e:
        util.logexc(
            LOG,
            f"Could not determine status of module {module_name}:{NL}{str(e)}",
        )

    return loaded


def unload(modules: list):
    """Unloads a list of kernel module

    This function unloads a list of kernel modules.

    @param distro_cfg: Distro config
    @param modules: list of module names

    @raises RuntimeError
    """

    cmd = copy.copy(DEFAULT_CONFIG["km_cmd"]["unload"])
    for module in set(modules):
        cmd.append(module)
        try:
            if is_loaded(module):
                LOG.debug("Unloading kernel module %s", module)
                subp.subp(cmd)
        except subp.ProcessExecutionError as e:
            raise RuntimeError(
                f"Could not unload kernel module {module}:{NL}{str(e)}"
            ) from e


def update_initial_ramdisk():
    """Update initramfs for all installed kernels

    @param distro_cfg: Distro config

    @raises RuntimeError
    """
    try:
        subp.subp(DEFAULT_CONFIG["km_cmd"]["update"])
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            f"Failed to update initial ramdisk:{NL}{str(e)}"
        ) from e


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    kernel_modules_section = None
    unload_modules = []  # type: list

    kernel_modules_section = util.get_cfg_option_list(
        cfg, "kernel_modules", []
    )

    if not kernel_modules_section:
        LOG.debug(
            "Skipping module named %s, no "
            "'kernel_modules' configuration found",
            name,
        )
        return

    LOG.debug("Found kernel_modules section in config")

    # check systemd usage
    if not cloud.distro.uses_systemd():
        LOG.debug(
            "Skipping module named %s, due to " "no systemd installed",
            name,
        )
        return

    # cleanup
    LOG.info("Cleaning up kernel modules")
    cleanup()

    # iterate over modules
    for module in kernel_modules_section:
        # check schema
        supplemental_schema_validation(module)

        # Load module
        if module.get("load", True):
            prepare_module(module["name"])
        else:
            unload_modules.append(module["name"])

        # Enhance module
        if module.get("persist"):
            enhance_module(module["name"], module["persist"], unload_modules)

    # rebuild initial ramdisk
    log.info("Update initramfs")
    update_initial_ramdisk()

    # Unload modules (blacklisted or 'load' is false)
    log.info("Unloading kernel modules")
    unload(unload_modules)

    # reload kernel modules
    log.info("Reloading kernel modules")
    reload_modules(cloud)
