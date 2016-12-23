# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Package Update Upgrade Install
------------------------------
**Summary:** update, upgrade, and install packages

This module allows packages to be updated, upgraded or installed during boot.
If any packages are to be installed or an upgrade is to be performed then the
package cache will be updated first. If a package installation or upgrade
requires a reboot, then a reboot can be performed if
``package_reboot_if_required`` is specified. A list of packages to install can
be provided. Each entry in the list can be either a package name or a list with
two entries, the first being the package name and the second being the specific
package version to install.

**Internal name:** ``cc_package_update_upgrade_install``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    packages:
        - pwgen
        - pastebinit
        - [libpython2.7, 2.7.3-0ubuntu3.1]
    package_update: <true/false>
    package_upgrade: <true/false>
    package_reboot_if_required: <true/false>

    apt_update: (alias for package_update)
    apt_upgrade: (alias for package_upgrade)
    apt_reboot_if_required: (alias for package_reboot_if_required)
"""

import os
import time

from cloudinit import log as logging
from cloudinit import util

REBOOT_FILE = "/var/run/reboot-required"
REBOOT_CMD = ["/sbin/reboot"]


def _multi_cfg_bool_get(cfg, *keys):
    for k in keys:
        if util.get_cfg_option_bool(cfg, k, False):
            return True
    return False


def _fire_reboot(log, wait_attempts=6, initial_sleep=1, backoff=2):
    util.subp(REBOOT_CMD)
    start = time.time()
    wait_time = initial_sleep
    for _i in range(0, wait_attempts):
        time.sleep(wait_time)
        wait_time *= backoff
        elapsed = time.time() - start
        log.debug("Rebooted, but still running after %s seconds", int(elapsed))
    # If we got here, not good
    elapsed = time.time() - start
    raise RuntimeError(("Reboot did not happen"
                        " after %s seconds!") % (int(elapsed)))


def handle(_name, cfg, cloud, log, _args):
    # Handle the old style + new config names
    update = _multi_cfg_bool_get(cfg, 'apt_update', 'package_update')
    upgrade = _multi_cfg_bool_get(cfg, 'package_upgrade', 'apt_upgrade')
    reboot_if_required = _multi_cfg_bool_get(cfg, 'apt_reboot_if_required',
                                             'package_reboot_if_required')
    pkglist = util.get_cfg_option_list(cfg, 'packages', [])

    errors = []
    if update or len(pkglist) or upgrade:
        try:
            cloud.distro.update_package_sources()
        except Exception as e:
            util.logexc(log, "Package update failed")
            errors.append(e)

    if upgrade:
        try:
            cloud.distro.package_command("upgrade")
        except Exception as e:
            util.logexc(log, "Package upgrade failed")
            errors.append(e)

    if len(pkglist):
        try:
            cloud.distro.install_packages(pkglist)
        except Exception as e:
            util.logexc(log, "Failed to install packages: %s", pkglist)
            errors.append(e)

    # TODO(smoser): handle this less violently
    # kernel and openssl (possibly some other packages)
    # write a file /var/run/reboot-required after upgrading.
    # if that file exists and configured, then just stop right now and reboot
    reboot_fn_exists = os.path.isfile(REBOOT_FILE)
    if (upgrade or pkglist) and reboot_if_required and reboot_fn_exists:
        try:
            log.warn("Rebooting after upgrade or install per %s", REBOOT_FILE)
            # Flush the above warning + anything else out...
            logging.flushLoggers(log)
            _fire_reboot(log)
        except Exception as e:
            util.logexc(log, "Requested reboot did not happen!")
            errors.append(e)

    if len(errors):
        log.warn("%s failed with exceptions, re-raising the last one",
                 len(errors))
        raise errors[-1]

# vi: ts=4 expandtab
