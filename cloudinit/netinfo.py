# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import cloudinit.util as util

from prettytable import PrettyTable


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

        fieldpost = ""
        if toks[0] == "inet6":
            fieldpost = "6"

        for i in range(len(toks)):
            if toks[i] == "hwaddr":
                try:
                    devs[curdev]["hwaddr"] = toks[i + 1]
                except IndexError:
                    pass
            for field in ("addr", "bcast", "mask"):
                target = "%s%s" % (field, fieldpost)
                if devs[curdev].get(target, ""):
                    continue
                if toks[i] == "%s:" % field:
                    try:
                        devs[curdev][target] = toks[i + 1]
                    except IndexError:
                        pass
                elif toks[i].startswith("%s:" % field):
                    devs[curdev][target] = toks[i][len(field) + 1:]

    if empty != "":
        for (_devname, dev) in devs.iteritems():
            for field in dev:
                if dev[field] == "":
                    dev[field] = empty

    return devs


def route_info():
    (route_out, _err) = util.subp(["route", "-n"])
    routes = []
    entries = route_out.splitlines()[1:]
    for line in entries:
        if not line:
            continue
        toks = line.split()
        if len(toks) < 8 or toks[0] == "Kernel" or toks[0] == "Destination":
            continue
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
        routes.append(entry)
    return routes


def getgateway():
    routes = []
    try:
        routes = route_info()
    except:
        pass
    for r in routes:
        if r['flags'].find("G") >= 0:
            return "%s[%s]" % (r['gateway'], r['iface'])
    return None


def netdev_pformat():
    lines = []
    try:
        netdev = netdev_info(empty=".")
    except Exception:
        lines.append(util.center("Net device info failed", '!', 80))
        netdev = None
    if netdev is not None:
        fields = ['Device', 'Up', 'Address', 'Mask', 'Hw-Address']
        tbl = PrettyTable(fields)
        for (dev, d) in netdev.iteritems():
            tbl.add_row([dev, d["up"], d["addr"], d["mask"], d["hwaddr"]])
        netdev_s = tbl.get_string()
        max_len = len(max(netdev_s.splitlines(), key=len))
        header = util.center("Net device info", "+", max_len)
        lines.extend([header, netdev_s])
    return "\n".join(lines)


def route_pformat():
    lines = []
    try:
        routes = route_info()
    except Exception:
        lines.append(util.center('Route info failed', '!', 80))
        routes = None
    if routes is not None:
        fields = ['Route', 'Destination', 'Gateway',
                  'Genmask', 'Interface', 'Flags']
        tbl = PrettyTable(fields)
        for (n, r) in enumerate(routes):
            route_id = str(n)
            tbl.add_row([route_id, r['destination'],
                        r['gateway'], r['genmask'],
                        r['iface'], r['flags']])
        route_s = tbl.get_string()
        max_len = len(max(route_s.splitlines(), key=len))
        header = util.center("Route info", "+", max_len)
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
