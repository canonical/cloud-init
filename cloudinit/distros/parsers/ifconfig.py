# Copyright(C) 2022 Mina Galić
#
# Author: Mina Galić <me+FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import re
from cloudinit import log as logging
from typing import Tuple
from ipaddress import IPv4Interface, IPv4Address, IPv6Interface

LOG = logging.getLogger(__name__)


DEFAULT_IF = {
    "inet": [],
    "inet6": [],
    "mac": "",
    "macs": [],
    "up": False,
    "options": [],
}


# see man ifconfig(8)
# - https://man.freebsd.org/ifconfig(8)
# - https://man.netbsd.org/ifconfig.8
# - https://man.openbsd.org/ifconfig.8
class Ifconfig:
    def __init__(self):
        self._ifs = {}

    def parse(self, text: str) -> dict:
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
                ifs[curif] = copy.deepcopy(self._parse_flags(toks))
            if toks[0].startswith("capabilities="):
                flags = re.split(r"<|>", toks[0])
                ifs[curif]["flags"].append(flags)

            if toks[0] == "description:":
                ifs[curif]["description"] = line[line.index(":") + 2 :]

            if (
                toks[0].startswith("options=")
                or toks[0].startswith("ec_capabilities")
                or toks[0].startswith("ec_enabled")
            ):
                options = re.split(r"<|>", toks[0])
                if len(options) > 1:
                    ifs[curif]["options"].append(options[1].split(","))

            if toks[0] == "ether":
                ifs[curif]["mac"] = toks[1]
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "hwaddr":
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "groups:":
                ifs[curif]["groups"] = toks[1:]

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

        return ifs

    def _parse_inet(self, toks: list) -> Tuple[str, dict]:
        if "/" in toks[1]:
            ip = IPv4Interface(toks[1])
            netmask = ip.netmask
            broadcast = toks[3]
        else:
            netmask = str(IPv4Address(int(toks[3], 0)))
            broadcast = toks[5]
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

    def _parse_inet6(self, toks: list) -> Tuple[str, dict]:
        if "/" in toks[1]:
            ip = IPv6Interface(toks[1])
            prefixlen = toks[1].split("/")[1]
        else:
            for i in range(2, len(toks)):
                if toks[i] == "prefixlen":
                    prefixlen = toks[i + 1]
                    break
            ip = IPv6Interface("%s/%s" % (toks[1], prefixlen))

        if ip.is_link_local:
            scope = "link-local"
        elif ip.is_site_local:
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
