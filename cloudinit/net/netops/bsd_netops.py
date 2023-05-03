from typing import Optional

import cloudinit.net.netops as netops
from cloudinit import subp


class BsdNetOps(netops.NetOps):
    @staticmethod
    def link_up(interface: str):
        subp.subp(["ifconfig", interface, "up"])

    @staticmethod
    def link_down(interface: str):
        subp.subp(["ifconfig", interface, "down"])

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
    def get_default_route() -> str:
        pass

    @staticmethod
    def add_addr(interface: str, address: str, broadcast: str):
        pass

    @staticmethod
    def del_addr(interface: str, address: str):
        pass
