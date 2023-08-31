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

    def update_package_sources(self):
        pass

    def install_packages(self, pkglist: Iterable[str]) -> UninstalledPackages:
        # Snap doesn't provide us with a mechanism to know which packages
        # are available or have failed, so install one at a time
        pkglist = util.expand_package_list("%s=%s", list(pkglist))
        failed: List[str] = []
        for pkg in pkglist:
            try:
                subp.subp(["snap", "install"] + pkg.split("="))
            except subp.ProcessExecutionError:
                failed.append(pkg)
                LOG.info("Snap failed to install package: %s", pkg)
        return failed

    @staticmethod
    def upgrade_packages():
        subp.subp(["snap", "refresh"])
