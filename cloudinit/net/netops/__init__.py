from abc import abstractmethod
from typing import Optional

from cloudinit.subp import SubpResult


class NetOps:
    @staticmethod
    @abstractmethod
    def link_up(interface: str) -> SubpResult:
        pass

    @staticmethod
    @abstractmethod
    def link_down(interface: str) -> SubpResult:
        pass

    @staticmethod
    @abstractmethod
    def link_rename(current_name: str, new_name: str):
        pass

    @staticmethod
    def add_route(
        interface: str,
        route: str,
        *,
        gateway: Optional[str] = None,
        source_address: Optional[str] = None
    ):
        pass

    @staticmethod
    def append_route(interface: str, address: str, gateway: str):
        pass

    @staticmethod
    def del_route(
        interface: str,
        address: str,
        *,
        gateway: Optional[str] = None,
        source_address: Optional[str] = None
    ):
        pass

    @staticmethod
    @abstractmethod
    def get_default_route() -> str:
        pass

    @staticmethod
    def add_addr(
        interface: str, address: str, broadcast: Optional[str] = None
    ):
        pass

    @staticmethod
    def del_addr(interface: str, address: str):
        pass

    @staticmethod
    def flush_addr(interface: str):
        pass
