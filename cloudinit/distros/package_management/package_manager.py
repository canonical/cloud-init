from abc import ABC, abstractmethod
from typing import Iterable, List, MutableMapping, Type

from cloudinit import helpers

UninstalledPackages = List[str]
known_package_managers: MutableMapping[str, Type["PackageManager"]] = {}


class PackageManager(ABC):
    name: str

    def __init__(self, runner: helpers.Runners, **kwargs):
        self.runner = runner

    def __init_subclass__(cls) -> None:
        known_package_managers[cls.name] = cls

    @classmethod
    def from_config(cls, runner: helpers.Runners, cfg) -> "PackageManager":
        return cls(runner)

    @abstractmethod
    def update_package_sources(self):
        ...

    @abstractmethod
    def install_packages(self, pkglist: Iterable[str]) -> UninstalledPackages:
        ...
