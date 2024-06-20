# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Package Update Upgrade Install: update, upgrade, and install packages"""

import logging
import os
import time

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.log import flush_loggers
from cloudinit.settings import PER_INSTANCE

REBOOT_FILES = ("/var/run/reboot-required", "/run/reboot-needed")
REBOOT_CMD = ["/sbin/reboot"]

meta: MetaSchema = {
    "id": "cc_package_update_upgrade_install",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [
        "apt_update",
        "package_update",
        "apt_upgrade",
        "package_upgrade",
        "packages",
    ],
}  # type: ignore

LOG = logging.getLogger(__name__)


def _multi_cfg_bool_get(cfg, *keys):
    for k in keys:
        if util.get_cfg_option_bool(cfg, k, False):
            return True
    return False


def _fire_reboot(
    wait_attempts: int = 6, initial_sleep: int = 1, backoff: int = 2
):
    """Run a reboot command and panic if it doesn't happen fast enough."""
    subp.subp(REBOOT_CMD)
    start = time.monotonic()
    wait_time = initial_sleep
    for _i in range(wait_attempts):
        time.sleep(wait_time)
        wait_time *= backoff
        elapsed = time.monotonic() - start
        LOG.debug("Rebooted, but still running after %s seconds", int(elapsed))
    # If we got here, not good
    elapsed = time.monotonic() - start
    raise RuntimeError(
        "Reboot did not happen after %s seconds!" % (int(elapsed))
    )


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # Handle the old style + new config names
    update = _multi_cfg_bool_get(cfg, "apt_update", "package_update")
    upgrade = _multi_cfg_bool_get(cfg, "package_upgrade", "apt_upgrade")
    reboot_if_required = _multi_cfg_bool_get(
        cfg, "apt_reboot_if_required", "package_reboot_if_required"
    )
    pkglist = util.get_cfg_option_list(cfg, "packages", [])

    errors = []
    if update or upgrade:
        try:
            cloud.distro.update_package_sources()
        except Exception as e:
            util.logexc(LOG, "Package update failed")
            errors.append(e)

    if upgrade:
        try:
            cloud.distro.package_command("upgrade")
        except Exception as e:
            util.logexc(LOG, "Package upgrade failed")
            errors.append(e)

    if len(pkglist):
        try:
            cloud.distro.install_packages(pkglist)
        except Exception as e:
            util.logexc(
                LOG, "Failure when attempting to install packages: %s", pkglist
            )
            errors.append(e)

    # TODO(smoser): handle this less violently
    # kernel and openssl (possibly some other packages)
    # write a file /var/run/reboot-required after upgrading.
    # if that file exists and configured, then just stop right now and reboot
    for reboot_marker in REBOOT_FILES:
        reboot_fn_exists = os.path.isfile(reboot_marker)
        if reboot_fn_exists:
            break
    if (upgrade or pkglist) and reboot_if_required and reboot_fn_exists:
        try:
            LOG.warning(
                "Rebooting after upgrade or install per %s", reboot_marker
            )
            # Flush the above warning + anything else out...
            flush_loggers(LOG)
            _fire_reboot()
        except Exception as e:
            util.logexc(LOG, "Requested reboot did not happen!")
            errors.append(e)

    if len(errors):
        LOG.warning(
            "%s failed with exceptions, re-raising the last one", len(errors)
        )
        raise errors[-1]
