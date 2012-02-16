#!/usr/bin/python
# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import subprocess


def netdev_info(empty=""):
    fields = ("hwaddr", "addr", "bcast", "mask")
    ifcfg_out = str(subprocess.check_output(["ifconfig", "-a"]))
    devs = {}
    for line in ifcfg_out.splitlines():
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

    return(devs)


def route_info():
    route_out = str(subprocess.check_output(["route", "-n"]))
    routes = []
    for line in route_out.splitlines()[1:]:
        if not line:
            continue
        toks = line.split()
        if toks[0] == "Kernel" or toks[0] == "Destination":
            continue
        routes.append(toks)
    return(routes)


def getgateway():
    for r in route_info():
        if r[3].find("G") >= 0:
            return("%s[%s]" % (r[1], r[7]))
    return(None)


def debug_info(pre="ci-info: "):
    lines = []
    try:
        netdev = netdev_info(empty=".")
    except Exception:
        lines.append("netdev_info failed!")
        netdev = {}
    for (dev, d) in netdev.iteritems():
        lines.append("%s%-6s: %i %-15s %-15s %s" %
            (pre, dev, d["up"], d["addr"], d["mask"], d["hwaddr"]))
    try:
        routes = route_info()
    except Exception:
        lines.append("route_info failed")
        routes = []
    n = 0
    for r in routes:
        lines.append("%sroute-%d: %-15s %-15s %-15s %-6s %s" %
            (pre, n, r[0], r[1], r[2], r[7], r[3]))
        n = n + 1
    return('\n'.join(lines))


if __name__ == '__main__':
    print debug_info()
