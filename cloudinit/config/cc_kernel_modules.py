# This file is part of cloud-init. See LICENSE file for license information.

"""Kernel Modules"""
from array import array
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = dedent(
    """\
"""
)

meta: MetaSchema = {
    "id": "cc_kernel_modules",
    "name": "Kernel Modules",
    "title": "Module to load/blacklist/enhance kernel modules",
    "description": MODULE_DESCRIPTION,
    "distros": ["debian", "ubuntu"],
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
DEFAULT_CONFIG_FILES = {
    "load": {
        "path": "/etc/modules-load.d/cloud-init.conf",
        "permissions": 0o600,
    },
    "persist": {
        "path": "/etc/modprobe.d/cloud-init.conf",
        "permissions": 0o600,
    },
}


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
                    f"persist:{key}. Found {value}"
                )
        elif key == "blacklist":
            if not isinstance(value, bool):
                errors.append(
                    "Expected a boolean for kernel_modules:"
                    f"persist:{key}. Found {value}"
                )
        elif key == "softdep":
            for sdkey, sdvalue in sorted(key.items()):
                if sdkey in ("pre", "post"):
                    if not isinstance(sdvalue, array):
                        errors.append(
                            "Expected an array for kernel_modules:persist:"
                            f"softdep:{sdkey}. Found {sdvalue}"
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
                    f"{key}. Found {value}"
                )
        elif key == "load":
            if not isinstance(value, bool):
                errors.append(
                    "Expected a boolean for kernel_modules:"
                    f"{key}. Found {value}"
                )
        elif key == "persist":
            errors.append(persist_schema_validation(key))

    if errors:
        raise ValueError(
            f"Invalid kernel_modules configuration:{NL}{NL.join(errors)}"
        )


def load_module_on_boot(module_name: str):
    """Prepare kernel module to be loaded on boot.

    This function appends a kernel module to a file
    (depends on operating system) for loading a module on boot.

    @param module_name: string.

    @raises: RuntimeError when write operation fails.
    """

    try:
        LOG.debug("Appending kernel module %s", module_name)
        util.write_file(
            DEFAULT_CONFIG_FILES["load"]["path"],
            module_name,
            DEFAULT_CONFIG_FILES["load"]["permissions"],
            omode="a",
        )
    except Exception as e:
        raise RuntimeError(
            f"Failure appending kernel module '{module_name}' to file "
            f' {DEFAULT_CONFIG_FILES["load"]["path"]}:{NL}{str(e)}'
        ) from e


def enhance_module(module_name: str, persist: dict):
    """Enhances a kernel modules behavior

    This function appends specific settings and options
    for a kernel module, which will be applied when kernel
    module get's loaded.

    @param module_name: string.
    @param persist: Dictionary

    @raises: RuntimeError when write operation fails.
    """

    for (key, value) in persist.items():
        LOG.debug(
            "Enhancing kernel module %s with %s:%s", module_name, key, value
        )
        entry = f"{key} {module_name} {value}"
        # softdep special case
        if key == "softdep":
            entry += " pre:".join({key["pre"]}) + " post: ".join({key["post"]})

        try:
            util.write_file(
                DEFAULT_CONFIG_FILES["persist"]["path"],
                entry,
                DEFAULT_CONFIG_FILES["persist"]["permissions"],
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

    @raises: RuntimeError when remove operation fails
    """
    for config_file in DEFAULT_CONFIG_FILES:
        LOG.debug("Removing file %s", config_file["path"])
        try:
            util.del_file(config_file["path"])
        except Exception as e:
            raise RuntimeError(
                f"Could not delete file {config_file['path']}:{NL}{str(e)}"
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


def update_initial_ramdisk():
    """Update initramfs for all installed kernels

    @raises RuntimeError
    """
    try:
        subp.subp(["update-initramfs", "-u", "-k", "all"])
    except subp.ProcessExecutionError() as e:
        raise RuntimeError(
            f"Failed to update initial ramdisk:{NL}{str(e)}"
        ) from e


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    kernel_modules_section = None

    if "kernel_modules" in cfg:
        LOG.debug("Found kernel_modules section in config")
        kernel_modules_section = cfg["kernel_modules"]
    else:
        LOG.debug(
            "Skipping module named %s, no "
            "'kernel_modules' configuration found",
            name,
        )
        return

    # check schema
    supplemental_schema_validation(kernel_modules_section)

    # iterate over modules
    for module in kernel_modules_section.items():
        # cleanup when module has no elements
        if not kernel_modules_section:
            LOG.info("Cleaning up kernel modules")
            cleanup()
        # Load module
        if module["load"]:
            LOG.info(
                "Writing %s file for loading kernel modules on boot",
                DEFAULT_CONFIG_FILES["load"]["path"],
            )
            load_module_on_boot(module["name"])

        # Enhance module
        enhance_module(module["name"], module["persist"])

    # rebuild initial ramdisk
    log.info("Update initramfs")
    update_initial_ramdisk()

    # reload kernel modules
    log.info("Reloading kernel modules")
    reload_modules(cloud)
