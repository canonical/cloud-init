# Copyright(C) 2022 FreeBSD Foundation
#
# Author: Mina Galić <me+FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import re
from ipaddress import IPv4Address, IPv4Interface, IPv6Interface
from typing import Dict, Optional, Tuple

from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class Ifstate:
    def __init__(self, name):
        self.name = name
        self.inet = {}
        self.inet6 = {}
        self.up = False
        self.options = []
        self.nd6 = []
        self.flags = []
        self.mtu: int = 0
        self.metric: int = 0
        self.groups = []
        self.description: Optional[str] = None
        self.media: Optional[str] = None
        self.status: Optional[str] = None
        self.mac: Optional[str] = None
        self.macs = []
        self.vlan = {}
        self.members = []

    @property
    def is_loopback(self) -> bool:
        if "loopback" in self.flags or ("lo" in self.groups):
            return True
        return False

    @property
    def is_physical(self) -> bool:
        # OpenBSD makes this very easy:
        if "egress" in self.groups:
            return True
        if self.groups == [] and self.media and "Ethernet" in self.media:
            return True
        return False

    @property
    def is_bridge(self) -> bool:
        if "bridge" in self.groups:
            return True
        if self.members:
            return True
        return False

    @property
    def is_vlan(self) -> bool:
        if "vlan" in self.groups or self.vlan:
            return True
        return False


# see man ifconfig(8)
# - https://man.freebsd.org/ifconfig(8)
# - https://man.netbsd.org/ifconfig.8
# - https://man.openbsd.org/ifconfig.8
class Ifconfig:
    def __init__(self):
        self._ifs = {}

    def parse(self, text: str) -> Dict[str, Ifstate]:
        for line in text.splitlines():
            if len(line) == 0:
                continue
            if line[0] not in ("\t", " "):
                curif = line.split()[0]
                # current ifconfig pops a ':' on the end of the device
                if curif.endswith(":"):
                    curif = curif[:-1]
                dev = Ifstate(curif)
                self._ifs[curif] = dev

            toks = line.lower().strip().split()

            if len(toks) > 1 and toks[1].startswith("flags="):
                flags = self._parse_flags(toks)
                dev.flags = copy.deepcopy(flags["flags"])
                dev.up = flags["up"]
                dev.mtu = flags["mtu"]
                dev.metric = flags["metric"]
            if toks[0].startswith("capabilities="):
                caps = re.split(r"<|>", toks[0])
                dev.flags.append(caps)

            if toks[0] == "description:":
                dev.description = line[line.index(":") + 2 :]

            if (
                toks[0].startswith("options=")
                or toks[0].startswith("ec_capabilities")
                or toks[0].startswith("ec_enabled")
            ):
                options = re.split(r"<|>", toks[0])
                if len(options) > 1:
                    dev.options += options[1].split(",")

            if toks[0] == "ether":
                dev.mac = toks[1]
                dev.macs.append(toks[1])

            if toks[0] == "hwaddr":
                dev.macs.append(toks[1])

            if toks[0] == "groups:":
                dev.groups += toks[1:]

            if toks[0] == "media:":
                dev.media = line[line.index(": ") + 2 :]

            if toks[0] == "nd6":
                nd6_opts = re.split(r"<|>", toks[0])
                if len(nd6_opts) > 1:
                    dev.nd6 = nd6_opts[1].split(",")

            if toks[0] == "status":
                dev.status = toks[1]

            if toks[0] == "inet":
                ip = self._parse_inet(toks)
                dev.inet[ip[0]] = copy.deepcopy(ip[1])

            if toks[0] == "inet6":
                ip = self._parse_inet6(toks)
                dev.inet6[ip[0]] = copy.deepcopy(ip[1])

            if toks[0] == "member:":
                dev.members += toks[1]

            if toks[0] == "vlan:":
                dev.vlan = {}
                dev.vlan["id"] = toks[1]
                for i in range(2, len(toks)):
                    if toks[i] == "interface:":
                        dev.vlan["link"] = toks[i + 1]

        return self._ifs

    def _parse_inet(self, toks: list) -> Tuple[str, dict]:
        broadcast = None
        if "/" in toks[1]:
            ip = IPv4Interface(toks[1])
            netmask = str(ip.netmask)
            if "broadcast" in toks:
                broadcast = toks[toks.index("broadcast") + 1]
        else:
            netmask = str(IPv4Address(int(toks[3], 0)))
            if "broadcast" in toks:
                broadcast = toks[toks.index("broadcast") + 1]
            ip = IPv4Interface("%s/%s" % (toks[1], netmask))

        prefixlen = ip.with_prefixlen.split("/")[1]
        return (
            str(ip.ip),
            {
                "netmask": netmask,
                "broadcast": broadcast,
                "prefixlen": prefixlen,
            },
        )

    def _get_prefixlen(self, toks):
        for i in range(2, len(toks)):
            if toks[i] == "prefixlen":
                return toks[i + 1]

    def _parse_inet6(self, toks: list) -> Tuple[str, dict]:
        scope = None
        # workaround https://github.com/python/cpython/issues/78969
        if "%" in toks[1]:
            scope = "link-local"
            ip6, rest = toks[1].split("%")
            if "/" in rest:
                prefixlen = rest.split("/")[1]
            else:
                prefixlen = self._get_prefixlen(toks)
            ip = IPv6Interface("%s/%s" % (ip6, prefixlen))
        elif "/" in toks[1]:
            ip = IPv6Interface(toks[1])
            prefixlen = toks[1].split("/")[1]
        else:
            prefixlen = self._get_prefixlen(toks)
            ip = IPv6Interface("%s/%s" % (toks[1], prefixlen))

        if not scope and ip.is_link_local:
            scope = "link-local"
        elif not scope and ip.is_site_local:
            scope = "site-local"

        return (str(ip.ip), {"prefixlen": prefixlen, "scope": scope})

    def _parse_flags(self, toks: list) -> dict:
        flags = re.split(r"<|>", toks[1])
        ret = {}
        if len(flags) > 1:
            ret["flags"] = flags[1].split(",")
            if "up" in ret["flags"]:
                ret["up"] = True
            if toks[2] == "metric":
                ret["metric"] = int(toks[3])
            if toks[4] == "mtu":
                ret["mtu"] = int(toks[5])
        return ret
