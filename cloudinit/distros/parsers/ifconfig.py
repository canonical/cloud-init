# Copyright(C) 2022 Mina Galić
#
# Author: Mina Galić <me+FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import re
from ipaddress import IPv4Address, IPv4Interface, IPv6Interface
from typing import List, Optional, Tuple

from cloudinit import log as logging

LOG = logging.getLogger(__name__)


DEFAULT_IF = {
    "inet": {},
    "inet6": {},
    "mac": None,
    "macs": [],
    "groups": [],
    "up": False,
    "options": [],
}


class Ifstate:
    def __init__(self, name, state):
        self._name = name
        self._state = copy.deepcopy(state)

    @property
    def name(self) -> str:
        return self._name

    @property
    def inet(self) -> Optional[dict]:
        if "inet" in self._state:
            return self._state["inet"]
        return None

    @property
    def inet6(self) -> Optional[dict]:
        if "inet6" in self._state:
            return self._state["inet6"]
        return None

    @property
    def up(self) -> bool:
        return self._state["up"]

    @property
    def options(self) -> List[str]:
        return self._state["options"]

    @property
    def nd6(self) -> List[str]:
        if "nd6_options" in self._state:
            return self._state["nd6_options"]
        return []

    @property
    def flags(self) -> List[str]:
        return self._state["flags"]

    @property
    def description(self) -> Optional[str]:
        if "description" in self._state:
            return self._state["description"]
        return None

    @property
    def media(self) -> Optional[str]:
        if "media" in self._state:
            return self._state["media"]
        return None

    @property
    def status(self) -> Optional[str]:
        if "status" in self._state:
            return self._state["status"]
        return None

    @property
    def mac(self) -> Optional[str]:
        return self._state["mac"]

    @property
    def vlan(self) -> Optional[dict]:
        if "status" in self._state:
            return self._state["vlan"]
        return None

    @property
    def macs(self) -> List[str]:
        if self._state["macs"] != []:
            return self._state["macs"]
        return []

    @property
    def groups(self) -> List[str]:
        # groups are so categorically useful, that it would be a shame to make
        # them optional
        return self._state["groups"]

    @property
    def members(self) -> Optional[List[str]]:
        if "members" in self._state:
            return self._state["members"]
        return None

    @property
    def is_loopback(self) -> bool:
        if "loopback" in self.flags or (
            self.groups and "lo" in self._state["groups"]
        ):
            return True
        return False

    @property
    def is_physical(self) -> bool:
        # OpenBSD makes this very easy:
        if self.groups and "egress" in self.groups:
            return True
        if not self.groups and self.media and "Ethernet" in self.media:
            return True
        return False

    @property
    def is_bridge(self) -> bool:
        if self.groups and "bridge" in self.groups:
            return True
        if self.members:
            return True
        return False

    @property
    def is_vlan(self) -> bool:
        if self.groups and "vlan" in self.groups:
            return True
        if "vlan" in self._state:
            return True
        return False


# see man ifconfig(8)
# - https://man.freebsd.org/ifconfig(8)
# - https://man.netbsd.org/ifconfig.8
# - https://man.openbsd.org/ifconfig.8
class Ifconfig:
    def __init__(self):
        self._ifs = []

    def parse(self, text: str) -> List[Ifstate]:
        ifs = {}
        for line in text.splitlines():
            if len(line) == 0:
                continue
            if line[0] not in ("\t", " "):
                curif = line.split()[0]
                # current ifconfig pops a ':' on the end of the device
                if curif.endswith(":"):
                    curif = curif[:-1]
                if curif not in ifs:
                    ifs[curif] = copy.deepcopy(DEFAULT_IF)

            toks = line.lower().strip().split()

            if len(toks) > 1 and toks[1].startswith("flags="):
                flags = self._parse_flags(toks)
                ifs[curif]["flags"] = copy.deepcopy(flags["flags"])
                ifs[curif]["up"] = flags["up"]
                ifs[curif]["mtu"] = flags["mtu"]
                ifs[curif]["metric"] = flags["metric"]
            if toks[0].startswith("capabilities="):
                caps = re.split(r"<|>", toks[0])
                ifs[curif]["flags"].append(caps)

            if toks[0] == "description:":
                ifs[curif]["description"] = line[line.index(":") + 2 :]

            if (
                toks[0].startswith("options=")
                or toks[0].startswith("ec_capabilities")
                or toks[0].startswith("ec_enabled")
            ):
                options = re.split(r"<|>", toks[0])
                if len(options) > 1:
                    ifs[curif]["options"] += options[1].split(",")

            if toks[0] == "ether":
                ifs[curif]["mac"] = toks[1]
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "hwaddr":
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "groups:":
                ifs[curif]["groups"] += toks[1:]

            if toks[0] == "media:":
                ifs[curif]["media"] = line[line.index(": ") + 2 :]

            if toks[0] == "nd6":
                nd6_opts = re.split(r"<|>", toks[0])
                if len(nd6_opts) > 1:
                    ifs[curif]["nd6_options"] = nd6_opts[1].split(",")

            if toks[0] == "status":
                ifs[curif]["status"] = toks[1]

            if toks[0] == "inet":
                ip = self._parse_inet(toks)
                ifs[curif]["inet"][ip[0]] = copy.deepcopy(ip[1])

            if toks[0] == "inet6":
                ip = self._parse_inet6(toks)
                ifs[curif]["inet6"][ip[0]] = copy.deepcopy(ip[1])

            if toks[0] == "member:":
                if "members" in ifs[curif]:
                    ifs[curif]["members"] += toks[1]
                else:
                    ifs[curif]["members"] = [toks[1]]

            if toks[0] == "vlan:":
                ifs[curif]["vlan"] = {}
                ifs[curif]["vlan"]["id"] = toks[1]
                for i in range(2, len(toks)):
                    if toks[i] == "interface:":
                        ifs[curif]["vlan"]["link"] = toks[i + 1]

        for i in ifs:
            ifstate = Ifstate(i, ifs[i])
            self._ifs.append(ifstate)
        return self._ifs

    def _parse_inet(self, toks: list) -> Tuple[str, dict]:
        broadcast = None
        if "/" in toks[1]:
            ip = IPv4Interface(toks[1])
            netmask = ip.netmask
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
