# This file is part of cloud-init. See LICENSE file for license information.

"""Kernel Modules"""
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
Manages and enhances kernel modules on a systemd-based system.
This module is capable of loading kernel modules at boot as well as
enhancing it with parameters.
Beside applying settings during runtime it will also persist all
settings in ``/etc/modules-load.d`` and ``/etc/modprobe.d``.
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
    "load": {
        "path": "/etc/modules-load.d/50-cloud-init.conf",
        "permissions": 0o600,
    },
    "persist": {
        "path": "/etc/modprobe.d/50-cloud-init.conf",
        "permissions": 0o600,
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
            for sdkey, sdvalues in sorted(persist[key].items()):
                if sdkey not in ("pre", "post"):
                    errors.append(
                        "Unexpected key kernel_modules:persist:{sdkey}."
                        " Should be one of: pre, post"
                    )
                else:
                    if not isinstance(sdvalues, array):
                        errors.append(
                            "Expected an array for"
                            f" kernel_modules:persist:softdep:{sdkey}."
                            f" Found {sdvalues}."
                        )
                    for sditem in sdvalues:
                        if not isinstance(sditem, str):
                            "Expected array of strings for"
                            f" kernel_modules:persist:softdep:{sdkey}."
                            " Found {sditem}."
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

    try:
        LOG.debug("Appending kernel module %s", module_name)
        util.write_file(
            DEFAULT_CONFIG["load"]["path"],
            module_name + NL,
            DEFAULT_CONFIG["load"]["permissions"],
            omode="a",
        )
    except Exception as e:
        raise RuntimeError(
            f"Failure appending kernel module '{module_name}' to file "
            f'{DEFAULT_CONFIG["load"]["path"]}:{NL}{str(e)}'
        ) from e


def enhance_module(module_name: str, persist: dict, unload_modules: list):
    """Enhances a kernel module's behaviour

    This function appends specific settings and options
    for a kernel module, which will be applied when the kernel
    module gets loaded.

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
                DEFAULT_CONFIG["persist"]["path"],
                entry + NL,
                DEFAULT_CONFIG["persist"]["permissions"],
                omode="a",
            )
        except Exception as e:
            raise RuntimeError(
                f"Failure enhancing kernel module '{module_name}':{NL}{str(e)}"
            ) from e


def cleanup():
    """Clean up all kernel specific files

    This function removes all files that are
    responsible for loading and enhancing kernel modules.

    @raises RuntimeError when remove operation fails
    """

    LOG.debug("Cleaning up kernel modules")
    for action in sorted(DEFAULT_CONFIG.keys()):
        file_path = DEFAULT_CONFIG[action]["path"]
        LOG.debug("Removing file %s", file_path)
        try:
            util.del_file(file_path)
        except Exception as e:
            raise RuntimeError(
                f"Could not delete file {file_path}:{NL}{str(e)}"
            ) from e


def reload_modules(cloud: Cloud):
    """Reload kernel modules

    This function reloads modules in /etc/modules-load.d/50-cloud-init.conf
    with 'systemd-modules-load' service.

    @raises RuntimeError
    """
    LOG.debug("Reloading kernel modules")
    try:
        (out, _err) = cloud.distro.manage_service(
            "restart", "systemd-modules-load"
        )
        if re.search("Failed", out):
            raise RuntimeError(out.stdout.strip())
    except (subp.ProcessExecutionError, Exception) as e:
        raise RuntimeError(
            f"Could not load modules with systemd-modules-load:{NL}{str(e)}"
        ) from e


def unload(cloud: Cloud, modules: list):
    """Unloads a list of kernel module

    This function unloads a list of kernel modules.

    @param distro_cfg: Distro config
    @param modules: list of module names

    @raises RuntimeError
    """
    (out, _err) = cloud.distro.manage_kernel_module("list")
    loaded_modules = out.splitlines()
    for module in set(modules):
        if module in loaded_modules:
            try:
                cloud.distro.manage_kernel_module("unload", module)
            except subp.ProcessExecutionError as e:
                raise RuntimeError(
                    f"Could not unload kernel module {module}:{NL}{str(e)}"
                ) from e


def update_initial_ramdisk(cloud: Cloud):
    """Update initramfs for all installed kernels

    :param distro_cfg: Distro config

    :raises: RuntimeError on command failure to update initramfs
             NotImplementedError on lack of distro support
    """
    if not cloud.distro.update_initramfs_cmd:
        raise NotImplementedError(
            "Unable to update initramfs for %s. Kernel module changes will not"
            " persist across reboot",
            cloud.distro.name,
        )
    try:
        subp.subp(cloud.distro.update_initramfs_cmd)
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

    # check systemd usage
    if not cloud.distro.uses_systemd():
        LOG.debug(
            "Skipping module named %s, due to " "no systemd installed",
            name,
        )
        return

    # cleanup
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
    update_initial_ramdisk(cloud)

    # Unload modules (blacklisted or 'load' is false)
    unload(cloud, unload_modules)

    # reload kernel modules
    reload_modules(cloud)
