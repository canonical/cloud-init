# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import re

from cloudinit import log as logging
from cloudinit import util

from prettytable import PrettyTable

LOG = logging.getLogger()


def netdev_info(empty=""):
    fields = ("hwaddr", "addr", "bcast", "mask")
    (ifcfg_out, _err) = util.subp(["ifconfig", "-a"])
    devs = {}
    for line in str(ifcfg_out).splitlines():
        if len(line) == 0:
            continue
        if line[0] not in ("\t", " "):
            curdev = line.split()[0]
            devs[curdev] = {"up": False}
            for field in fields:
                devs[curdev][field] = ""
        toks = line.lower().strip().split()
        if toks[0] == "up":
            devs[curdev]['up'] = True
        # If the output of ifconfig doesn't contain the required info in the
        # obvious place, use a regex filter to be sure.
        elif len(toks) > 1:
            if re.search(r"flags=\d+<up,", toks[1]):
                devs[curdev]['up'] = True

        fieldpost = ""
        if toks[0] == "inet6":
            fieldpost = "6"

        for i in range(len(toks)):
            # older net-tools (ubuntu) show 'inet addr:xx.yy',
            # newer (freebsd and fedora) show 'inet xx.yy'
            # just skip this 'inet' entry. (LP: #1285185)
            try:
                if ((toks[i] in ("inet", "inet6") and
                     toks[i + 1].startswith("addr:"))):
                    continue
            except IndexError:
                pass

            # Couple the different items we're interested in with the correct
            # field since FreeBSD/CentOS/Fedora differ in the output.
            ifconfigfields = {
                "addr:": "addr", "inet": "addr",
                "bcast:": "bcast", "broadcast": "bcast",
                "mask:": "mask", "netmask": "mask",
                "hwaddr": "hwaddr", "ether": "hwaddr",
                "scope": "scope",
            }
            for origfield, field in ifconfigfields.items():
                target = "%s%s" % (field, fieldpost)
                if devs[curdev].get(target, ""):
                    continue
                if toks[i] == "%s" % origfield:
                    try:
                        devs[curdev][target] = toks[i + 1]
                    except IndexError:
                        pass
                elif toks[i].startswith("%s" % origfield):
                    devs[curdev][target] = toks[i][len(field) + 1:]

    if empty != "":
        for (_devname, dev) in devs.items():
            for field in dev:
                if dev[field] == "":
                    dev[field] = empty

    return devs


def route_info():
    (route_out, _err) = util.subp(["netstat", "-rn"])

    routes = {}
    routes['ipv4'] = []
    routes['ipv6'] = []

    entries = route_out.splitlines()[1:]
    for line in entries:
        if not line:
            continue
        toks = line.split()
        # FreeBSD shows 6 items in the routing table:
        #  Destination  Gateway    Flags Refs    Use  Netif Expire
        #  default      10.65.0.1  UGS      0  34920 vtnet0
        #
        # Linux netstat shows 2 more:
        #  Destination  Gateway    Genmask  Flags MSS Window irtt Iface
        #  0.0.0.0      10.65.0.1  0.0.0.0  UG      0 0         0 eth0
        if (len(toks) < 6 or toks[0] == "Kernel" or
                toks[0] == "Destination" or toks[0] == "Internet" or
                toks[0] == "Internet6" or toks[0] == "Routing"):
            continue
        if len(toks) < 8:
            toks.append("-")
            toks.append("-")
            toks[7] = toks[5]
            toks[5] = "-"
        entry = {
            'destination': toks[0],
            'gateway': toks[1],
            'genmask': toks[2],
            'flags': toks[3],
            'metric': toks[4],
            'ref': toks[5],
            'use': toks[6],
            'iface': toks[7],
        }
        routes['ipv4'].append(entry)

    try:
        (route_out6, _err6) = util.subp(["netstat", "-A", "inet6", "-n"])
    except util.ProcessExecutionError:
        pass
    else:
        entries6 = route_out6.splitlines()[1:]
        for line in entries6:
            if not line:
                continue
            toks = line.split()
            if (len(toks) < 6 or toks[0] == "Kernel" or
                    toks[0] == "Proto" or toks[0] == "Active"):
                continue
            entry = {
                'proto': toks[0],
                'recv-q': toks[1],
                'send-q': toks[2],
                'local address': toks[3],
                'foreign address': toks[4],
                'state': toks[5],
            }
            routes['ipv6'].append(entry)
    return routes


def getgateway():
    try:
        routes = route_info()
    except Exception:
        pass
    else:
        for r in routes.get('ipv4', []):
            if r['flags'].find("G") >= 0:
                return "%s[%s]" % (r['gateway'], r['iface'])
    return None


def netdev_pformat():
    lines = []
    try:
        netdev = netdev_info(empty=".")
    except Exception:
        lines.append(util.center("Net device info failed", '!', 80))
    else:
        fields = ['Device', 'Up', 'Address', 'Mask', 'Scope', 'Hw-Address']
        tbl = PrettyTable(fields)
        for (dev, d) in netdev.items():
            tbl.add_row([dev, d["up"], d["addr"], d["mask"], ".", d["hwaddr"]])
            if d.get('addr6'):
                tbl.add_row([dev, d["up"],
                             d["addr6"], ".", d.get("scope6"), d["hwaddr"]])
        netdev_s = tbl.get_string()
        max_len = len(max(netdev_s.splitlines(), key=len))
        header = util.center("Net device info", "+", max_len)
        lines.extend([header, netdev_s])
    return "\n".join(lines)


def route_pformat():
    lines = []
    try:
        routes = route_info()
    except Exception as e:
        lines.append(util.center('Route info failed', '!', 80))
        util.logexc(LOG, "Route info failed: %s" % e)
    else:
        if routes.get('ipv4'):
            fields_v4 = ['Route', 'Destination', 'Gateway',
                         'Genmask', 'Interface', 'Flags']
            tbl_v4 = PrettyTable(fields_v4)
            for (n, r) in enumerate(routes.get('ipv4')):
                route_id = str(n)
                tbl_v4.add_row([route_id, r['destination'],
                                r['gateway'], r['genmask'],
                                r['iface'], r['flags']])
            route_s = tbl_v4.get_string()
            max_len = len(max(route_s.splitlines(), key=len))
            header = util.center("Route IPv4 info", "+", max_len)
            lines.extend([header, route_s])
        if routes.get('ipv6'):
            fields_v6 = ['Route', 'Proto', 'Recv-Q', 'Send-Q',
                         'Local Address', 'Foreign Address', 'State']
            tbl_v6 = PrettyTable(fields_v6)
            for (n, r) in enumerate(routes.get('ipv6')):
                route_id = str(n)
                tbl_v6.add_row([route_id, r['proto'],
                                r['recv-q'], r['send-q'],
                                r['local address'], r['foreign address'],
                                r['state']])
            route_s = tbl_v6.get_string()
            max_len = len(max(route_s.splitlines(), key=len))
            header = util.center("Route IPv6 info", "+", max_len)
            lines.extend([header, route_s])
    return "\n".join(lines)


def debug_info(prefix='ci-info: '):
    lines = []
    netdev_lines = netdev_pformat().splitlines()
    if prefix:
        for line in netdev_lines:
            lines.append("%s%s" % (prefix, line))
    else:
        lines.extend(netdev_lines)
    route_lines = route_pformat().splitlines()
    if prefix:
        for line in route_lines:
            lines.append("%s%s" % (prefix, line))
    else:
        lines.extend(route_lines)
    return "\n".join(lines)

# vi: ts=4 expandtab
