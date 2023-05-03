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
        subp.subp(["route", "add", route, "-interface", interface])
        if gateway and gateway != "0.0.0.0":
            subp.subp(
                ["route", "change", route, gateway],
            )

    @staticmethod
    def append_route(interface: str, address: str, gateway: str):
        return BsdNetOps.add_route(interface, address=address, gateway=gateway)

    @staticmethod
    def del_route(
        interface: str,
        address: str,
        *,
        gateway: Optional[str] = None,
        source_address: Optional[str] = None
    ):
        subp.subp(
            ["route", "-4", "del"]
            + (["-net", address] if "/" in address else ["-host", address])
            + ["-interface", interface]
            + ([gateway] if gateway and gateway != "0.0.0.0" else []),
        )

    @staticmethod
    def get_default_route() -> str:
        std, _ = subp.subp(["route", "-4v", "get", "0.0.0.0/0"])
        return std.splitlines()[-1].strip()

    @staticmethod
    def add_addr(interface: str, address: str, broadcast: str):
        pass

    @staticmethod
    def del_addr(interface: str, address: str):
        pass
