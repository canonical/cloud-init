# Copyright (C) 2026 Red Hat, Inc.
#
# Author: Ani Sinha <anisinha@redhat.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""RHEL: Configure RHEL-specific settings and services"""

import logging
import os
from typing import Any, Dict, Optional

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_rhel",
    "distros": ["rhel", "centos", "fedora"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["rhel"],
}

LOG = logging.getLogger(__name__)

FIPS_HELPER_PATH = "/usr/libexec/"
FIPS_HELPER = "fips-setup-helper"
FIPS_MODE_FLAG = "/proc/sys/crypto/fips_enabled"
EFI_SYSFS = "/sys/firmware/efi"
ESP = "/boot/efi"
RHEL_UTILITY_FILES = {
    "fips": "%s/%s" % (FIPS_HELPER_PATH, FIPS_HELPER),
}


def esp_rh_path() -> str:
    variant = util.system_info()["variant"]
    return "redhat" if variant == "rhel" else variant


def grub_uki_name() -> str:
    uname_arch = os.uname()[4]
    if uname_arch == "x86_64":
        return "grubx64.efi"
    elif uname_arch == "aarch64":
        return "grubaa64.efi"
    raise NotImplementedError("platform is not supported")


RH_ESP = "EFI/%s" % esp_rh_path()


def is_efi_boot() -> bool:
    return os.path.exists(EFI_SYSFS)


def _fips_mode_enabled() -> bool:
    if os.path.exists(FIPS_MODE_FLAG):
        return util.fips_enabled()

    # else read kernel command line
    cmdline = util.get_cmdline()
    if "fips=1" in cmdline:
        return True
    return False


def find_boot() -> Optional[str]:
    boot_part = [
        "findmnt",
        "--noheadings",
        "-o",
        "SOURCE",
        "/boot",
    ]
    info = None
    # find the boot partition
    try:
        info, _err = subp.subp(boot_part)
    except subp.ProcessExecutionError as e:
        # if /boot partition was not found, pass.
        if e.exit_code == 1:
            pass
        else:
            LOG.debug(
                "Error while trying to find info on /boot: %s",
                e,
            )
    return info


def find_boot_uuid(boot_dev: Optional[str]) -> Optional[str]:
    if not boot_dev:
        return None

    boot_uuid = ["blkid", "--output", "value", "--match-tag", "UUID", boot_dev]
    uuid = None
    try:
        uuid, _err = subp.subp(boot_uuid)
    except subp.ProcessExecutionError as e:
        util.logexc(
            LOG,
            "Error while trying to find UUID: %s",
            e,
        )
    return uuid


def update_kernel_commandline_grubby() -> None:
    boot_uuid = find_boot_uuid(find_boot())
    args = '"fips=1'

    if boot_uuid:
        args = args + " boot=UUID=%s" % boot_uuid

    args = args + '"'

    grubby = [
        "grubby",
        "--update-kernel=ALL",
        "--args=%s" % args,
    ]
    try:
        _out, _err = subp.subp(grubby)
    except subp.ProcessExecutionError as e:
        util.logexc(
            LOG,
            "Error while trying to update kernel commandline: %s",
            e,
        )
        raise e


def uses_grub_boot() -> bool:
    grub_uki = os.path.join(ESP, RH_ESP, grub_uki_name())
    LOG.debug(
        "Looking for grub UKI %s",
        grub_uki,
    )
    # if grub UKI exists in ESP, then its booted through grub
    return os.path.exists(grub_uki)


def _configure_fips(config: Dict[str, Any], cloud: Cloud) -> None:
    """Configure FIPS for RHEL"""

    if "fips_mode" not in config:
        LOG.warning("FIPS config option not provided!")
        return

    if not util.get_cfg_option_bool(config, "fips_mode", False):
        LOG.debug(
            "Fips mode is set to False",
        )
        return

    if _fips_mode_enabled():
        # fips mode already enabled
        return

    # RHEL cloud images have the following variants:
    # - booted off with non-uefi (traditional) boot with grub as the boot
    #   loader. This is mostly for older guests (v1 for Azure for example).
    # - booted off with UEFI using shim -> grub -> linux. These are for
    #   newer modern guests that support secure boot (v2 and above for Azure).
    # - Confidential guests that use UEFI but do not use grub. Their boot
    #   mechanism involves shim -> kernel UKI directly. So far, only CVMs
    #  (confidential virtual machines) do not use grub and perform direct boot.
    # In the following we distinguish between CVMs and non-CVM UEFI booted
    # guests.
    if is_efi_boot() and not uses_grub_boot():
        LOG.info(
            "Fips mode cannot be enabled with EFI direct kernel boot for now",
        )
        return

    fips_helper = os.path.join(FIPS_HELPER_PATH, FIPS_HELPER)

    if not os.path.exists(fips_helper):
        LOG.debug("fips mode enabler %s does not exist", fips_helper)
        return

    try:
        subp.subp(
            [fips_helper, "cloud-init"],
        )
    except subp.ProcessExecutionError as e:
        util.logexc(
            LOG,
            "Failed to enable FIPS mode with %s: %s",
            FIPS_HELPER,
            e,
        )
        return

    try:
        # update the kernel command line to add fips=1
        update_kernel_commandline_grubby()
    except Exception as e:
        util.logexc(
            LOG,
            "Failed to enable FIPS mode in the kernel commandline: %s" % e,
        )
        return

    # remove non-fips complaint ssh keys
    for keyname in util.FIPS_UNSUPPORTED_KEY_NAMES:
        keyfile = util.KEY_FILE_TPL % (keyname)
        if os.path.exists(keyfile):
            try:
                util.del_file(keyfile)
            except Exception:
                util.logexc(LOG, "Failed deleting key file %s", keyfile)

    try:
        # initiate reboot
        LOG.warning("initiating reboot after updating kernel commandline")
        util.fire_reboot()
    except SystemExit:
        pass


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    """Configure RHEL-specific settings.

    Args:
        name: The module name
        cfg: Cloud-init configuration object
        cloud: Cloud object
        args: Command line arguments (unused)
    """
    rhel_config = cfg.get("rhel", {})
    if not rhel_config:
        LOG.debug("No RHEL configuration found, skipping")
        return

    LOG.info("Configuring RHEL-specific settings")

    # Configure individual components
    _configure_fips(rhel_config, cloud)

    LOG.info("RHEL configuration completed")
