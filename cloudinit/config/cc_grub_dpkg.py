# Copyright (C) 2009-2010, 2020 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Matthew Ruffell <matthew.ruffell@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Grub Dpkg: Configure grub debconf installation device"""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import ProcessExecutionError

MODULE_DESCRIPTION = """\
"""
meta: MetaSchema = {
    "id": "cc_grub_dpkg",
    "distros": ["ubuntu", "debian"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


def fetch_idevs():
    """
    Fetches the /dev/disk/by-id device grub is installed to.
    Falls back to plain disk name if no by-id entry is present.
    """
    disk = ""
    devices = []

    # BIOS mode systems use /boot and the disk path,
    # EFI mode systems use /boot/efi and the partition path.
    probe_target = "disk"
    probe_mount = "/boot"
    if is_efi_booted():
        probe_target = "device"
        probe_mount = "/boot/efi"

    try:
        # get the root disk where the /boot directory resides.
        disk = subp.subp(
            ["grub-probe", "-t", probe_target, probe_mount], capture=True
        ).stdout.strip()
    except ProcessExecutionError as e:
        # grub-common may not be installed, especially on containers
        # FileNotFoundError is a nested exception of ProcessExecutionError
        if isinstance(e.reason, FileNotFoundError):
            LOG.debug("'grub-probe' not found in $PATH")
        # disks from the container host are present in /proc and /sys
        # which is where grub-probe determines where /boot is.
        # it then checks for existence in /dev, which fails as host disks
        # are not exposed to the container.
        elif "failed to get canonical path" in e.stderr:
            LOG.debug("grub-probe 'failed to get canonical path'")
        else:
            # something bad has happened, continue to log the error
            raise
    except Exception:
        util.logexc(LOG, "grub-probe failed to execute for grub_dpkg")

    if not disk or not os.path.exists(disk):
        # If we failed to detect a disk, we can return early
        return ""

    try:
        # check if disk exists and use udevadm to fetch symlinks
        devices = (
            subp.subp(
                ["udevadm", "info", "--root", "--query=symlink", disk],
                capture=True,
            )
            .stdout.strip()
            .split()
        )
    except Exception:
        util.logexc(
            LOG, "udevadm DEVLINKS symlink query failed for disk='%s'", disk
        )

    LOG.debug("considering these device symlinks: %s", ",".join(devices))
    # filter symlinks for /dev/disk/by-id entries
    devices = [dev for dev in devices if "disk/by-id" in dev]
    LOG.debug("filtered to these disk/by-id symlinks: %s", ",".join(devices))
    # select first device if there is one, else fall back to plain name
    idevs = sorted(devices)[0] if devices else disk
    LOG.debug("selected %s", idevs)

    return idevs


def is_efi_booted() -> bool:
    """
    Check if the system is booted in EFI mode.
    """
    try:
        return os.path.exists("/sys/firmware/efi")
    except OSError as e:
        LOG.error("Failed to determine if system is booted in EFI mode: %s", e)
        # If we can't determine if we're booted in EFI mode, assume we're not.
        return False


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    mycfg = cfg.get("grub_dpkg", cfg.get("grub-dpkg", {}))
    if not mycfg:
        mycfg = {}

    enabled = mycfg.get("enabled", True)
    if util.is_false(enabled):
        LOG.debug("%s disabled by config grub_dpkg/enabled=%s", name, enabled)
        return

    dconf_sel = get_debconf_config(mycfg)
    LOG.debug("Setting grub debconf-set-selections with '%s'", dconf_sel)

    try:
        subp.subp(["debconf-set-selections"], data=dconf_sel)
    except Exception as e:
        util.logexc(
            LOG, "Failed to run debconf-set-selections for grub_dpkg: %s", e
        )


def get_debconf_config(mycfg: Config) -> str:
    """
    Returns the debconf config for grub-pc or
    grub-efi depending on the systems boot mode.
    """
    if is_efi_booted():
        idevs = util.get_cfg_option_str(
            mycfg, "grub-efi/install_devices", None
        )

        if idevs is None:
            idevs = fetch_idevs()

        return "grub-pc grub-efi/install_devices string %s\n" % idevs
    else:
        idevs = util.get_cfg_option_str(mycfg, "grub-pc/install_devices", None)
        if idevs is None:
            idevs = fetch_idevs()

        idevs_empty = mycfg.get("grub-pc/install_devices_empty")
        if idevs_empty is None:
            idevs_empty = not idevs
        elif not isinstance(idevs_empty, bool):
            idevs_empty = util.translate_bool(idevs_empty)
        idevs_empty = str(idevs_empty).lower()

        # now idevs and idevs_empty are set to determined values
        # or, those set by user
        return (
            "grub-pc grub-pc/install_devices string %s\n"
            "grub-pc grub-pc/install_devices_empty boolean %s\n"
            % (idevs, idevs_empty)
        )
