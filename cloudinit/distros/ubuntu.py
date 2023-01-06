# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
from contextlib import suppress
from typing import List

from cloudinit import subp
from cloudinit.distros import PREFERRED_NTP_CLIENTS, debian


def get_available_apt_packages(pkglist) -> List[str]:
    apt_packages = []
    for pkg in pkglist:
        output: str = subp.subp(
            ["apt-cache", "search", "--names-only", f"^{pkg}$"]
        ).stdout.strip()
        if output:
            apt_packages.append(pkg)
    return apt_packages


def get_available_snap_packages(pkglist) -> List[str]:
    snap_packages = []
    for pkg in pkglist:
        with suppress(subp.ProcessExecutionError):
            subp.subp(["snap", "info", pkg])
            snap_packages.append(pkg)
    return snap_packages


class Distro(debian.Distro):
    def __init__(self, name, cfg, paths):
        super(Distro, self).__init__(name, cfg, paths)
        # Ubuntu specific network cfg locations
        self.network_conf_fn = {
            "eni": "/etc/network/interfaces.d/50-cloud-init.cfg",
            "netplan": "/etc/netplan/50-cloud-init.yaml",
        }
        self.renderer_configs = {
            "eni": {
                "eni_path": self.network_conf_fn["eni"],
                "eni_header": debian.NETWORK_FILE_HEADER,
            },
            "netplan": {
                "netplan_path": self.network_conf_fn["netplan"],
                "netplan_header": debian.NETWORK_FILE_HEADER,
                "postcmds": True,
            },
        }

    @property
    def preferred_ntp_clients(self):
        """The preferred ntp client is dependent on the version."""
        if not self._preferred_ntp_clients:
            self._preferred_ntp_clients = copy.deepcopy(PREFERRED_NTP_CLIENTS)
        return self._preferred_ntp_clients

    def install_snap_packages(self, pkglist):
        for pkg in pkglist:
            subp.subp(["snap", "install", pkg])

    def install_packages(self, pkglist):
        """Install packages from either apt or snap.

        We prefer apt here as to not unexpectedly install a snap when
        a user was previously using an apt installed package. This will result
        in a snap install needing to wait for an apt update. If you know your
        package is a snap, call "install_snap_packages" directly.
        """
        if not subp.which("snap"):
            return super().install_packages(pkglist)

        # We need to update sources before checking apt cache
        super().update_package_sources()

        apt_packages = get_available_apt_packages(pkglist)
        remaining_packages = [p for p in pkglist if p not in apt_packages]
        snap_packages = get_available_snap_packages(remaining_packages)
        remaining_packages = [
            p for p in remaining_packages if p not in snap_packages
        ]
        if remaining_packages:
            raise ValueError(
                f"Could not find package(s) {remaining_packages} "
                "in apt or snap."
            )

        if apt_packages:
            self.package_command("install", pkgs=apt_packages)
        if snap_packages:
            self.install_snap_packages(snap_packages)
