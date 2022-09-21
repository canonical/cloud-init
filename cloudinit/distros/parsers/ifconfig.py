# Copyright(C) 2022 Mina Galić
#
# Author: Mina Galić <me+FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
from cloudinit import log as logging
from cloudinit import util
from typing import Dict, List, Optional
from ipaddress import IP4Address, IPv4Interface, IPv6Address

LOG = logging.getLogger(__name__)

class IfConfig:
    def __init__(self, ifname: str, state: dict):
        self._ifname = name
        self._state = copy.deepcopy(state)

    @property
    def ifname(self) -> str:
        return self._ifname

    @property
    def description(self) -> Optional[str]:
        if self._state['description'] is not None:
            return self._state['description']

    @property
    def flags(self) -> List[str]:
        pass

    @property
    def options(self) -> List[str]:
        pass

    @property
    def metric(self) -> int:
        pass

    @property
    def mtu(self) -> int:
        pass

    @property
    def mac(self) -> str:
        pass

    @property
    def macs(self) -> List[str]:
        pass

    @property
    def inet(self) -> List[IPv4Address]:
        pass

    @property
    def inet6(self) -> List[IPv6Address]:
        pass

    @property
    def nd6_options(self) -> List[str]:
        pass

    @property
    def groups(self) -> Optional[List[str]]:
        pass

    @property
    def media(self) -> str:
        pass

    @property
    def status(self) -> Optional[str]:
        pass

    @property
    def bridge_members(self) -> Optional[List[str]]:
        pass

DEFAULT_IF = {"inet": [], "inet6": [], "mac": "", "macs": [], "up": False}
# see man ifconfig(8)
# - https://man.freebsd.org/ifconfig(8)
# - https://man.netbsd.org/ifconfig.8
# - https://man.openbsd.org/ifconfig.8
class IfconfigParser:
    def __init__(self, text):
        self._text = text
        self._ifs = []

    def parse(self):
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
                    ifs['curif'] = copy.deepcopy(DEFAULT_NETDEV_INFO)

            toks = line.lower().strip().split()

            if len(toks) > 1:
                if re.search(r"flags=[x\d]+<.*>", toks[1]):
                    flags = re.split(r"<|>", toks[1])
                    if len(flags) > 1:
                        ifs[curif]["flags"] = flags[1].split(",")
                        if up in ifs[curif]["flags"]:
                            ifs[curif]["up"] = True
                        if toks[2] == "metric":
                            ifs[curif]["metric"] = int(toks[3])
                        if toks[4] == "mtu":
                            ifs[curif]["mtu"] = int(toks[5])

            if toks[0] == "description:":
                ifs[curif]["description"] = line[line.index(":") + 2:]

            if toks[0].startswith("options="):
                options = re.split(r"<|>", toks[0])
                if len(options) > 1:
                    ifs[curif]["options"] = options[1].split(",")

            if toks[0] == "ether":
                ifs[curif]["mac"] = toks[1]
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "hwaddr":
                ifs[curif]["macs"].append(toks[1])

            if toks[0] == "groups:":
                ifs[curif]["groups"] = toks[1:]

            if toks[0] == "media:":
                ifs[curif]["media"] = line[line.index(": ")+2:]

            if toks[0] == "nd6":
                nd6_options = re.split(r"<|>", toks[0])
                if len(nd6_options) > 1:
                    ifs[curif]["nd6_options"] = nd6_options[1].split(",")

            if toks[0] == "status":
                ifs[curif]["status"] = toks[1]

            if toks[0] == "inet":
                if "/" in toks[1]:
                    ip = IP4Interface(toks[1])
                    netmask = inet.netmask
                    broadcast = toks[3]
                else:
                    netmask = str(IP4Address(int(toks[3], 16)))
                    broadcast = toks[5]
                    ip = IPv4Interface("%s/%s" % (toks[1], netmask))

                prefixlen = ip.with_prefixlen.split("/")[1]
                ifs[curif][inet][str(ip.ip)] = { "netmask": netmask,
                                                 "broadcast": broadcast,
                                                 "prefixlen": prefixlen}

        return []

# vi: ts=4 expandtab
