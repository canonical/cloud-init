# Copyright(C) 2022 FreeBSD Foundation
#
# Author: Mina Galić <me+FreeBSD@igalic.co>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
import re
from collections import defaultdict
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Interface, IPv6Interface
from typing import Dict, List, Optional, Tuple, Union

LOG = logging.getLogger(__name__)


class Ifstate:
    """
    This class holds the parsed state of a BSD network interface.
    It is itself side-effect free.
    All methods with side-effects should be implemented on one of the
    ``BSDNetworking`` classes.
    """

    def __init__(self, name):
        self.name = name
        self.index: int = 0
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
        return "loopback" in self.flags or "lo" in self.groups

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
        return "bridge" in self.groups

    @property
    def is_bond(self) -> bool:
        return "lagg" in self.groups

    @property
    def is_vlan(self) -> bool:
        return ("vlan" in self.groups) or (self.vlan != {})


class Ifconfig:
    """
    A parser for BSD style ``ifconfig(8)`` output.
    For documentation here:
    - https://man.freebsd.org/ifconfig(8)
    - https://man.netbsd.org/ifconfig.8
    - https://man.openbsd.org/ifconfig.8
    All output is considered equally, and then massaged into a singular form:
    an ``Ifstate`` object.
    """

    def __init__(self):
        self._ifs_by_name = {}
        self._ifs_by_mac = {}

    @lru_cache()
    def parse(self, text: str) -> Dict[str, Union[Ifstate, List[Ifstate]]]:
        """
        Parse the ``ifconfig -a`` output ``text``, into a dict of ``Ifstate``
        objects, referenced by ``name`` *and* by ``mac`` address.

        This dict will always be the same, given the same input, so we can
        ``@lru_cache()`` it. n.b.: ``@lru_cache()`` takes only the
        ``__hash__()`` of the input (``text``), so it should be fairly quick,
        despite our giant inputs.

        @param text: The output of ``ifconfig -a``
        @returns: A dict of ``Ifstate``s, referenced by ``name`` and ``mac``
        """
        ifindex = 0
        ifs_by_mac = defaultdict(list)
        dev = None
        for line in text.splitlines():
            if len(line) == 0:
                continue
            if line[0] not in ("\t", " "):
                # We hit the start of a device block in the ifconfig output
                # These start with devN: flags=NNNN<flags> and then continue
                # *indented* for the rest of the config.
                # Here our loop resets ``curif`` & ``dev`` to this new device
                ifindex += 1
                curif = line.split()[0]
                # current ifconfig pops a ':' on the end of the device
                if curif.endswith(":"):
                    curif = curif[:-1]
                dev = Ifstate(curif)
                dev.index = ifindex
                self._ifs_by_name[curif] = dev

            if not dev:
                # This shouldn't happen with normal ifconfig output, but
                # if it does, ensure we don't Traceback
                continue

            toks = line.lower().strip().split()

            if len(toks) > 1 and toks[1].startswith("flags="):
                flags = self._parse_flags(toks)
                if flags != {}:
                    dev.flags = copy.deepcopy(flags["flags"])
                    dev.up = flags["up"]
                    if "mtu" in flags:
                        dev.mtu = flags["mtu"]
                    if "metric" in flags:
                        dev.metric = flags["metric"]
            if toks[0].startswith("capabilities="):
                caps = re.split(r"<|>", toks[0])
                dev.flags.append(caps)

            if toks[0] == "index":
                # We have found a real index! override our fake one
                dev.index = int(toks[1])

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

            # We also store the Ifstate reference under all mac addresses
            # so we can easier reverse-find it.
            if toks[0] == "ether":
                dev.mac = toks[1]
                dev.macs.append(toks[1])
                ifs_by_mac[toks[1]].append(dev)
            if toks[0] == "hwaddr":
                dev.macs.append(toks[1])
                ifs_by_mac[toks[1]].append(dev)

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

            # bridges and ports are kind of the same thing, right?
            if toks[0] == "member:" or toks[0] == "laggport:":
                dev.members += toks[1]

            if toks[0] == "vlan:":
                dev.vlan = {}
                dev.vlan["id"] = toks[1]
                for i in range(2, len(toks)):
                    if toks[i] == "interface:":
                        dev.vlan["link"] = toks[i + 1]

        self._ifs_by_mac = dict(ifs_by_mac)
        return {**self._ifs_by_name, **self._ifs_by_mac}

    def ifs_by_mac(self):
        return self._ifs_by_mac

    def _parse_inet(self, toks: list) -> Tuple[str, dict]:
        broadcast = None
        if "/" in toks[1]:
            ip = IPv4Interface(toks[1])
            netmask = str(ip.netmask)
        else:
            netmask = str(IPv4Address(int(toks[3], 0)))
            ip = IPv4Interface("%s/%s" % (toks[1], netmask))

        if "broadcast" in toks:
            broadcast = toks[toks.index("broadcast") + 1]
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
            else:
                ret["up"] = False
            for t in range(2, len(toks)):
                if toks[t] == "metric":
                    ret["metric"] = int(toks[t + 1])
                elif toks[t] == "mtu":
                    ret["mtu"] = int(toks[t + 1])
        return ret
