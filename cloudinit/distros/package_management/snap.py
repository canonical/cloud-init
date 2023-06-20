import logging
from typing import List

from cloudinit import subp
from cloudinit.distros.package_management.package_manager import (
    PackageManager,
    UninstalledPackages,
)

LOG = logging.getLogger(__name__)


class Snap(PackageManager):
    name = "snap"

    def update_package_sources(self):
        pass

    def install_packages(self, pkglist: List[str]) -> UninstalledPackages:
        # Snap doesn't provide us with a mechanism to know which packages
        # are available or have failed, so install one at a time
        failed: List[str] = []
        for pkg in pkglist:
            try:
                subp.subp(["snap", "install", pkg])
            except subp.ProcessExecutionError:
                failed.append(pkg)
                LOG.debug("Snap failed to install package: %s", pkg)
        return failed
