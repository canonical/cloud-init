# This file is part of cloud-init. See LICENSE file for license information.
import logging
from typing import Iterable, List

from cloudinit import subp, util
from cloudinit.distros.package_management.package_manager import (
    PackageManager,
    UninstalledPackages,
)

LOG = logging.getLogger(__name__)


class Snap(PackageManager):
    name = "snap"

    def available(self) -> bool:
        return bool(subp.which("snap"))

    def update_package_sources(self, *, force=False):
        pass

    def install_packages(self, pkglist: Iterable) -> UninstalledPackages:
        # Snap doesn't provide us with a mechanism to know which packages
        # are available or have failed, so install one at a time
        pkglist = util.expand_package_list("%s=%s", list(pkglist))
        failed: List[str] = []
        for pkg in pkglist:
            try:
                subp.subp(["snap", "install"] + pkg.split("=", 1))
            except subp.ProcessExecutionError:
                failed.append(pkg)
                LOG.info("Failed to 'snap install %s'!", pkg)
        return failed

    @staticmethod
    def upgrade_packages():
        command = ["snap", "get", "system", "-d"]
        snap_hold = None
        try:
            result = subp.subp(command)
            snap_hold = (
                util.load_json(result.stdout).get("refresh", {}).get("hold")
            )
        except subp.ProcessExecutionError as e:
            LOG.info(
                "Continuing to snap refresh. Unable to run command: %s: %s",
                command,
                e,
            )
        if snap_hold == "forever":
            LOG.info(
                "Skipping snap refresh because refresh.hold is set to '%s'",
                snap_hold,
            )
        else:
            subp.subp(["snap", "refresh"])
