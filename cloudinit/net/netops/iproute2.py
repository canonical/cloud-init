from typing import Optional

from cloudinit import subp
from cloudinit.net.netops import NetOps


class Iproute2(NetOps):
    @staticmethod
    def link_up(
        interface: str, family: Optional[str] = None
    ) -> subp.SubpResult:
        family_args = []
        if family:
            family_args = ["-family", family]
        return subp.subp(
            ["ip", *family_args, "link", "set", "dev", interface, "up"]
        )

    @staticmethod
    def link_down(
        interface: str, family: Optional[str] = None
    ) -> subp.SubpResult:
        family_args = []
        if family:
            family_args = ["-family", family]
        return subp.subp(
            ["ip", *family_args, "link", "set", "dev", interface, "down"]
        )

    @staticmethod
    def link_rename(current_name: str, new_name: str):
        subp.subp(["ip", "link", "set", current_name, "name", new_name])

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
                "replace",
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
    def add_addr(
        interface: str, address: str, broadcast: Optional[str] = None
    ):
        broadcast_args = []
        if broadcast:
            broadcast_args = ["broadcast", broadcast]
        subp.subp(
            [
                "ip",
                "-family",
                "inet",
                "addr",
                "add",
                address,
                *broadcast_args,
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

    @staticmethod
    def flush_addr(interface: str):
        subp.subp(["ip", "flush", "dev", interface])
