from unittest import mock

from cloudinit.net.netops import iproute2
from cloudinit.subp import SubpResult


class TestOps:
    @mock.patch.object(iproute2.subp, "subp")
    def test_link_up(self, m_subp):
        iproute2.Iproute2.link_up("eth0")
        iproute2.Iproute2.link_up("eth0", "inet6")
        assert m_subp.call_args_list == [
            mock.call(["ip", "link", "set", "dev", "eth0", "up"]),
            mock.call(
                ["ip", "-family", "inet6", "link", "set", "dev", "eth0", "up"]
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_link_down(self, m_subp):
        iproute2.Iproute2.link_down("enp24s0")
        iproute2.Iproute2.link_down("eno1", "inet6")
        assert m_subp.call_args_list == [
            mock.call(["ip", "link", "set", "dev", "enp24s0", "down"]),
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet6",
                    "link",
                    "set",
                    "dev",
                    "eno1",
                    "down",
                ]
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_link_rename(self, m_subp):
        iproute2.Iproute2.link_rename("ens1", "ego1")
        assert m_subp.call_args_list == [
            mock.call(["ip", "link", "set", "ens1", "name", "ego1"])
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_add_route(self, m_subp):
        iproute2.Iproute2.add_route("wlan0", "102.42.42.0/24")
        iproute2.Iproute2.add_route(
            "ens2",
            "102.42.0.0/16",
            gateway="192.168.2.254",
            source_address="192.168.2.1",
        )
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "replace",
                    "102.42.42.0/24",
                    "dev",
                    "wlan0",
                ]
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "replace",
                    "102.42.0.0/16",
                    "via",
                    "192.168.2.254",
                    "dev",
                    "ens2",
                    "src",
                    "192.168.2.1",
                ]
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_del_route(self, m_subp):
        iproute2.Iproute2.del_route("wlan0", "102.42.42.0/24")
        iproute2.Iproute2.del_route(
            "ens2",
            "102.42.0.0/16",
            gateway="192.168.2.254",
            source_address="192.168.2.1",
        )
        assert m_subp.call_args_list == [
            mock.call(
                ["ip", "-4", "route", "del", "102.42.42.0/24", "dev", "wlan0"]
            ),
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "del",
                    "102.42.0.0/16",
                    "via",
                    "192.168.2.254",
                    "dev",
                    "ens2",
                    "src",
                    "192.168.2.1",
                ]
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_append_route(self, m_subp):
        iproute2.Iproute2.append_route("wlan0", "102.42.42.0/24", "10.0.4.254")
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "ip",
                    "-4",
                    "route",
                    "append",
                    "102.42.42.0/24",
                    "via",
                    "10.0.4.254",
                    "dev",
                    "wlan0",
                ]
            )
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_add_addr(self, m_subp):
        iproute2.Iproute2.add_addr("wlan0", "10.0.17.0", "10.0.17.255")
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "add",
                    "10.0.17.0",
                    "broadcast",
                    "10.0.17.255",
                    "dev",
                    "wlan0",
                ],
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_del_addr(self, m_subp):
        iproute2.Iproute2.del_addr("eth0", "10.0.8.3")
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "ip",
                    "-family",
                    "inet",
                    "addr",
                    "del",
                    "10.0.8.3",
                    "dev",
                    "eth0",
                ],
            ),
        ]

    @mock.patch.object(iproute2.subp, "subp")
    def test_flush_addr(self, m_subp):
        iproute2.Iproute2.flush_addr("eth0")
        assert m_subp.call_args_list == [
            mock.call(
                ["ip", "addr", "flush", "dev", "eth0"],
            ),
        ]

    @mock.patch.object(
        iproute2.subp,
        "subp",
        return_value=SubpResult(
            "default via 192.168.0.1 dev enp2s0 proto dhcp src 192.168.0.104"
            " metric 100",
            "",
        ),
    )
    def test_add_default_route(self, m_subp):
        assert iproute2.Iproute2.get_default_route() == (
            "default via 192.168.0.1 dev enp2s0 proto dhcp src"
            " 192.168.0.104 metric 100"
        )
        assert m_subp.call_args_list == [
            mock.call(
                [
                    "ip",
                    "route",
                    "show",
                    "0.0.0.0/0",
                ],
            ),
        ]
