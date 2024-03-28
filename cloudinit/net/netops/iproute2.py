from typing import Optional

import cloudinit.net.netops as netops
from cloudinit import subp


class Iproute2(netops.NetOps):
    @staticmethod
    def link_up(interface: str, family: Optional[str] = None):
        family_args = []
        if family:
            family_args = ["-family", family]
        subp.subp(["ip", *family_args, "link", "set", "dev", interface, "up"])

    @staticmethod
    def link_down(interface: str, family: Optional[str] = None):
        family_args = []
        if family:
            family_args = ["-family", family]
        subp.subp(
            ["ip", *family_args, "link", "set", "dev", interface, "down"]
        )

    @staticmethod
    def add_route(
        interface: str,
        route: str,
        *,
        gateway: Optional[str] = None,
        source_address: Optional[str] = None,
    ):
        gateway_args = []
        source_args = []
        if gateway and gateway != "0.0.0.0":
            gateway_args = ["via", gateway]
        if source_address:
            source_args = ["src", source_address]
        subp.subp(
            [
                "ip",
                "-4",
                "route",
                "add",
                route,
                *gateway_args,
                "dev",
                interface,
                *source_args,
            ]
        )

    @staticmethod
    def append_route(interface: str, address: str, gateway: str):
        gateway_args = []
        if gateway and gateway != "0.0.0.0":
            gateway_args = ["via", gateway]
        subp.subp(
            [
                "ip",
                "-4",
                "route",
                "append",
                address,
                *gateway_args,
                "dev",
                interface,
            ]
        )

    @staticmethod
    def del_route(
        interface: str,
        address: str,
        *,
        gateway: Optional[str] = None,
        source_address: Optional[str] = None,
    ):
        gateway_args = []
        source_args = []
        if gateway and gateway != "0.0.0.0":
            gateway_args = ["via", gateway]
        if source_address:
            source_args = ["src", source_address]
        subp.subp(
            [
                "ip",
                "-4",
                "route",
                "del",
                address,
                *gateway_args,
                "dev",
                interface,
                *source_args,
            ]
        )

    @staticmethod
    def get_default_route() -> str:
        return subp.subp(
            ["ip", "route", "show", "0.0.0.0/0"],
        ).stdout

    @staticmethod
    def add_addr(interface: str, address: str, broadcast: str):
        subp.subp(
            [
                "ip",
                "-family",
                "inet",
                "addr",
                "add",
                address,
                "broadcast",
                broadcast,
                "dev",
                interface,
            ],
            update_env={"LANG": "C"},
        )

    @staticmethod
    def del_addr(interface: str, address: str):
        subp.subp(
            ["ip", "-family", "inet", "addr", "del", address, "dev", interface]
        )
