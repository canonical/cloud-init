# This file is part of cloud-init. See LICENSE file for license information.
from abc import ABC, abstractmethod
from typing import Iterable, List

from cloudinit import helpers

UninstalledPackages = List[str]


class PackageManager(ABC):
    name: str

    def __init__(self, runner: helpers.Runners, **kwargs):
        self.runner = runner

    @classmethod
    def from_config(cls, runner: helpers.Runners, cfg) -> "PackageManager":
        return cls(runner)

    @abstractmethod
    def available(self) -> bool:
        """Return if package manager is installed on system."""

    @abstractmethod
    def update_package_sources(self, *, force=False):
        ...

    @abstractmethod
    def install_packages(self, pkglist: Iterable) -> UninstalledPackages:
        """Install the given packages.

        Return a list of packages that failed to install.
        Overriding classes should NOT raise an exception if packages failed
        to install. Instead, log the error and return what couldn't be
        installed so other installed package managers may be attempted.
        """
