# This file is part of cloud-init. See LICENSE file for license information.

"""Kernel Modules"""
import re
from array import array
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import uses_systemd
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = dedent(
    """\
"""
)

DISTROS = ["debian", "ubuntu"]

meta: MetaSchema = {
    "id": "cc_kernel_modules",
    "name": "Kernel Modules",
    "title": "Module to load/blacklist/enhance kernel modules",
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
DEFAULT_CONFIG = {
    "km_update_cmd": ["update-initramfs", "-u", "-k", "all"],
    "km_unload_cmd": ["rmmod"],
    "km_is_loaded_cmd": ["lsmod"],
    "km_files": {
        "load": {
            "path": "/etc/modules-load.d/cloud-init.conf",
            "permissions": 0o600,
        },
        "persist": {
            "path": "/etc/modprobe.d/cloud-init.conf",
            "permissions": 0o600,
        },
    },
}
DISTRO_OVERRIDES = {}  # type: dict
UNLOAD_MODULES = []  # type: list


def _distro_kernel_modules_configs(distro_name):
    """Return a distro-specific kernel_modules config dictionary

    @param distro_name: String providing the distro class name.
    @returns: Dict of distro configurations for kernel_modules.
    """
    cfg = DISTRO_OVERRIDES.get(distro_name, DEFAULT_CONFIG)
    return cfg


def persist_schema_validation(persist: dict):
    """Validate user-provided kernel_modules:persist option values.

    This function supplements flexible jsonschema validation with specific
    value checks to aid in triage of invalid user-provided configuration.

    @param kernel_module: Dictionary.

    @raises: ValueError describing invalid values provided.
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


def prepare_module(distro_cfg: dict, module_name: str):
    """Prepare kernel module to be loaded on boot.

    This function appends a kernel module to a file
    (depends on operating system) for loading a module on boot.

    @param distro_cfg: Distro config
    @param module_name: string.

    @raises: RuntimeError when write operation fails.
    """
    CFG_FILES = distro_cfg["km_files"]

    LOG.info(
        "Writing %s file for loading kernel modules on boot",
        CFG_FILES["load"]["path"],
    )

    try:
        LOG.debug("Appending kernel module %s", module_name)
        util.write_file(
            CFG_FILES["load"]["path"],
            module_name + NL,
            CFG_FILES["load"]["permissions"],
            omode="a",
        )
    except Exception as e:
        raise RuntimeError(
            f"Failure appending kernel module '{module_name}' to file "
            f'{CFG_FILES["load"]["path"]}:{NL}{str(e)}'
        ) from e


def enhance_module(distro_cfg: dict, module_name: str, persist: dict):
    """Enhances a kernel modules behavior

    This function appends specific settings and options
    for a kernel module, which will be applied when kernel
    module get's loaded.

    @param distro_cfg: Distro config
    @param module_name: string.
    @param persist: Dictionary

    @raises RuntimeError when write operation fails.
    """
    CFG_FILES = distro_cfg["km_files"]

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
                UNLOAD_MODULES.append(module_name)

        try:
            util.write_file(
                CFG_FILES["persist"]["path"],
                entry + NL,
                CFG_FILES["persist"]["permissions"],
                omode="a",
            )
        except Exception as e:
            raise RuntimeError(
                f"Failure enhancing kernel module '{module_name}':{NL}{str(e)}"
            ) from e


def cleanup(distro_cfg: dict):
    """Clean up all kernel specific files

    This function removes all files, which are
    responsible for loading and enhancing kernel modules.

    @param distro_cfg: Distro config

    @raises RuntimeError when remove operation fails
    """
    CFG_FILES = distro_cfg["km_files"]

    for (key, _) in sorted(CFG_FILES.items()):
        file_path = CFG_FILES[key]["path"]
        LOG.debug("Removing file %s", file_path)
        try:
            util.del_file(file_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not delete file {file_path}:{NL}{str(e)}"
            ) from e


def reload_modules(cloud: Cloud):
    """Reload kernel modules

    This function restarts service 'systemd-modules-load'
    for reloading kernel modules

    @param cloud: Cloud object

    @raises RuntimeError
    """
    try:
        cloud.distro.manage_service("restart", "systemd-modules-load")
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            f"Could not restart service systemd-modules-load:{NL}{str(e)}"
        ) from e


def is_loaded(distro_cfg: dict, module_name: str):
    """
    Checks if a kernel module is already loaded

    @param distro_cfg: Distro config
    @param module_name: name of kernel module
    """
    loaded = False
    try:
        out = subp.subp(
            distro_cfg["km_is_loaded_cmd"], capture=True, shell=True
        )
        if re.search("^" + module_name, out.stdout.strip()):
            loaded = True
    except subp.ProcessExecutionError as e:
        util.logexc(
            LOG,
            f"Could not determine status of module {module_name}:{NL}{str(e)}",
        )

    return loaded


def unload_modules(distro_cfg: dict, modules: list):
    """Unloads a list of kernel module

    This function unloads a list of kernel modules.

    @param distro_cfg: Distro config
    @param modules: list of module names

    @raises RuntimeError
    """
    for module in set(modules):
        cmd = distro_cfg["km_unload_cmd"].append(module)
        try:
            if is_loaded(distro_cfg, module):
                subp.subp(cmd)
        except subp.ProcessExecutionError as e:
            raise RuntimeError(
                f"Could not unload kernel module {module}:{NL}{str(e)}"
            ) from e


def update_initial_ramdisk(distro_cfg: dict):
    """Update initramfs for all installed kernels

    @param distro_cfg: Distro config

    @raises RuntimeError
    """
    try:
        subp.subp(distro_cfg["km_update_cmd"])
    except subp.ProcessExecutionError as e:
        raise RuntimeError(
            f"Failed to update initial ramdisk:{NL}{str(e)}"
        ) from e


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    kernel_modules_section = None

    if "kernel_modules" in cfg:
        LOG.debug("Found kernel_modules section in config")
        kernel_modules_section = util.get_cfg_option_list(
            cfg, "kernel_modules", []
        )
    else:
        LOG.debug(
            "Skipping module named %s, no "
            "'kernel_modules' configuration found",
            name,
        )
        return

    # check systemd usage
    if not uses_systemd:
        LOG.debug(
            "Skipping module named %s, due to " "no systemd installed",
            name,
        )
        return

    # create distro config
    distro_cfg = _distro_kernel_modules_configs(cloud.distro.name)

    # iterate over modules
    for module in kernel_modules_section:
        # check schema
        supplemental_schema_validation(module)

        # cleanup
        LOG.info("Cleaning up kernel modules")
        cleanup(distro_cfg)

        # Load module
        if module.get("load"):
            prepare_module(distro_cfg, module["name"])
        else:
            UNLOAD_MODULES.append(module["name"])

        # Enhance module
        if module.get("persist"):
            enhance_module(distro_cfg, module["name"], module["persist"])

    # rebuild initial ramdisk
    log.info("Update initramfs")
    update_initial_ramdisk(distro_cfg)

    # Unload modules (blacklisted or 'load' is false)
    log.info("Unloading kernel modules")
    unload_modules(distro_cfg, UNLOAD_MODULES)

    # reload kernel modules
    log.info("Reloading kernel modules")
    reload_modules(cloud)
