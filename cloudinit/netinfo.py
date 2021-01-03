# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from copy import copy, deepcopy
import re

from cloudinit import log as logging
from cloudinit.net.network_state import net_prefix_to_ipv4_mask
from cloudinit import subp
from cloudinit import util

from cloudinit.simpletable import SimpleTable

LOG = logging.getLogger()


DEFAULT_NETDEV_INFO = {
    "ipv4": [],
    "ipv6": [],
    "hwaddr": "",
    "up": False
}


def _netdev_info_iproute(ipaddr_out):
    """
    Get network device dicts from ip route and ip link info.

    @param ipaddr_out: Output string from 'ip addr show' command.

    @returns: A dict of device info keyed by network device name containing
              device configuration values.
    @raise: TypeError if ipaddr_out isn't a string.
    """
    devs = {}
    dev_name = None
    for num, line in enumerate(ipaddr_out.splitlines()):
        m = re.match(r'^\d+:\s(?P<dev>[^:]+):\s+<(?P<flags>\S+)>\s+.*', line)
        if m:
            dev_name = m.group('dev').lower().split('@')[0]
            flags = m.group('flags').split(',')
            devs[dev_name] = {
                'ipv4': [], 'ipv6': [], 'hwaddr': '',
                'up': bool('UP' in flags and 'LOWER_UP' in flags),
            }
        elif 'inet6' in line:
            m = re.match(
                r'\s+inet6\s(?P<ip>\S+)\sscope\s(?P<scope6>\S+).*', line)
            if not m:
                LOG.warning(
                    'Could not parse ip addr show: (line:%d) %s', num, line)
                continue
            devs[dev_name]['ipv6'].append(m.groupdict())
        elif 'inet' in line:
            m = re.match(
                r'\s+inet\s(?P<cidr4>\S+)(\sbrd\s(?P<bcast>\S+))?\sscope\s'
                r'(?P<scope>\S+).*', line)
            if not m:
                LOG.warning(
                    'Could not parse ip addr show: (line:%d) %s', num, line)
                continue
            match = m.groupdict()
            cidr4 = match.pop('cidr4')
            addr, _, prefix = cidr4.partition('/')
            if not prefix:
                prefix = '32'
            devs[dev_name]['ipv4'].append({
                'ip': addr,
                'bcast': match['bcast'] if match['bcast'] else '',
                'mask': net_prefix_to_ipv4_mask(prefix),
                'scope': match['scope']})
        elif 'link' in line:
            m = re.match(
                r'\s+link/(?P<link_type>\S+)\s(?P<hwaddr>\S+).*', line)
            if not m:
                LOG.warning(
                    'Could not parse ip addr show: (line:%d) %s', num, line)
                continue
            if m.group('link_type') == 'ether':
                devs[dev_name]['hwaddr'] = m.group('hwaddr')
            else:
                devs[dev_name]['hwaddr'] = ''
        else:
            continue
    return devs


def _netdev_info_ifconfig_netbsd(ifconfig_data):
    # fields that need to be returned in devs for each dev
    devs = {}
    for line in ifconfig_data.splitlines():
        if len(line) == 0:
            continue
        if line[0] not in ("\t", " "):
            curdev = line.split()[0]
            # current ifconfig pops a ':' on the end of the device
            if curdev.endswith(':'):
                curdev = curdev[:-1]
            if curdev not in devs:
                devs[curdev] = deepcopy(DEFAULT_NETDEV_INFO)
        toks = line.lower().strip().split()
        if len(toks) > 1:
            if re.search(r"flags=[x\d]+<up.*>", toks[1]):
                devs[curdev]['up'] = True

        for i in range(len(toks)):
            if toks[i] == "inet":  # Create new ipv4 addr entry
                network, net_bits = toks[i + 1].split('/')
                devs[curdev]['ipv4'].append(
                    {'ip': network, 'mask': net_prefix_to_ipv4_mask(net_bits)})
            elif toks[i] == "broadcast":
                devs[curdev]['ipv4'][-1]['bcast'] = toks[i + 1]
            elif toks[i] == "address:":
                devs[curdev]['hwaddr'] = toks[i + 1]
            elif toks[i] == "inet6":
                if toks[i + 1] == "addr:":
                    devs[curdev]['ipv6'].append({'ip': toks[i + 2]})
                else:
                    devs[curdev]['ipv6'].append({'ip': toks[i + 1]})
            elif toks[i] == "prefixlen":  # Add prefix to current ipv6 value
                addr6 = devs[curdev]['ipv6'][-1]['ip'] + "/" + toks[i + 1]
                devs[curdev]['ipv6'][-1]['ip'] = addr6
            elif toks[i].startswith("scope:"):
                devs[curdev]['ipv6'][-1]['scope6'] = toks[i].lstrip("scope:")
            elif toks[i] == "scopeid":
                res = re.match(r'.*<(\S+)>', toks[i + 1])
                if res:
                    devs[curdev]['ipv6'][-1]['scope6'] = res.group(1)
                else:
                    devs[curdev]['ipv6'][-1]['scope6'] = toks[i + 1]

    return devs


def _netdev_info_ifconfig(ifconfig_data):
    # fields that need to be returned in devs for each dev
    devs = {}
    for line in ifconfig_data.splitlines():
        if len(line) == 0:
            continue
        if line[0] not in ("\t", " "):
            curdev = line.split()[0]
            # current ifconfig pops a ':' on the end of the device
            if curdev.endswith(':'):
                curdev = curdev[:-1]
            if curdev not in devs:
                devs[curdev] = deepcopy(DEFAULT_NETDEV_INFO)
        toks = line.lower().strip().split()
        if toks[0] == "up":
            devs[curdev]['up'] = True
        # If the output of ifconfig doesn't contain the required info in the
        # obvious place, use a regex filter to be sure.
        elif len(toks) > 1:
            if re.search(r"flags=\d+<up,", toks[1]):
                devs[curdev]['up'] = True

        for i in range(len(toks)):
            if toks[i] == "inet":  # Create new ipv4 addr entry
                devs[curdev]['ipv4'].append(
                    {'ip': toks[i + 1].lstrip("addr:")})
            elif toks[i].startswith("bcast:"):
                devs[curdev]['ipv4'][-1]['bcast'] = toks[i].lstrip("bcast:")
            elif toks[i] == "broadcast":
                devs[curdev]['ipv4'][-1]['bcast'] = toks[i + 1]
            elif toks[i].startswith("mask:"):
                devs[curdev]['ipv4'][-1]['mask'] = toks[i].lstrip("mask:")
            elif toks[i] == "netmask":
                devs[curdev]['ipv4'][-1]['mask'] = toks[i + 1]
            elif toks[i] == "hwaddr" or toks[i] == "ether":
                devs[curdev]['hwaddr'] = toks[i + 1]
            elif toks[i] == "inet6":
                if toks[i + 1] == "addr:":
                    devs[curdev]['ipv6'].append({'ip': toks[i + 2]})
                else:
                    devs[curdev]['ipv6'].append({'ip': toks[i + 1]})
            elif toks[i] == "prefixlen":  # Add prefix to current ipv6 value
                addr6 = devs[curdev]['ipv6'][-1]['ip'] + "/" + toks[i + 1]
                devs[curdev]['ipv6'][-1]['ip'] = addr6
            elif toks[i].startswith("scope:"):
                devs[curdev]['ipv6'][-1]['scope6'] = toks[i].lstrip("scope:")
            elif toks[i] == "scopeid":
                res = re.match(r'.*<(\S+)>', toks[i + 1])
                if res:
                    devs[curdev]['ipv6'][-1]['scope6'] = res.group(1)
                else:
                    devs[curdev]['ipv6'][-1]['scope6'] = toks[i + 1]

    return devs


def netdev_info(empty=""):
    devs = {}
    if util.is_NetBSD():
        (ifcfg_out, _err) = subp.subp(["ifconfig", "-a"], rcs=[0, 1])
        devs = _netdev_info_ifconfig_netbsd(ifcfg_out)
    elif subp.which('ip'):
        # Try iproute first of all
        (ipaddr_out, _err) = subp.subp(["ip", "addr", "show"])
        devs = _netdev_info_iproute(ipaddr_out)
    elif subp.which('ifconfig'):
        # Fall back to net-tools if iproute2 is not present
        (ifcfg_out, _err) = subp.subp(["ifconfig", "-a"], rcs=[0, 1])
        devs = _netdev_info_ifconfig(ifcfg_out)
    else:
        LOG.warning(
            "Could not print networks: missing 'ip' and 'ifconfig' commands")

    if empty == "":
        return devs

    recurse_types = (dict, tuple, list)

    def fill(data, new_val="", empty_vals=("", b"")):
        """Recursively replace 'empty_vals' in data (dict, tuple, list)
           with new_val"""
        if isinstance(data, dict):
            myiter = data.items()
        elif isinstance(data, (tuple, list)):
            myiter = enumerate(data)
        else:
            raise TypeError("Unexpected input to fill")

        for key, val in myiter:
            if val in empty_vals:
                data[key] = new_val
            elif isinstance(val, recurse_types):
                fill(val, new_val)

    fill(devs, new_val=empty)
    return devs


def _netdev_route_info_iproute(iproute_data):
    """
    Get network route dicts from ip route info.

    @param iproute_data: Output string from ip route command.

    @returns: A dict containing ipv4 and ipv6 route entries as lists. Each
              item in the list is a route dictionary representing destination,
              gateway, flags, genmask and interface information.
    """

    routes = {}
    routes['ipv4'] = []
    routes['ipv6'] = []
    entries = iproute_data.splitlines()
    default_route_entry = {
        'destination': '', 'flags': '', 'gateway': '', 'genmask': '',
        'iface': '', 'metric': ''}
    for line in entries:
        entry = copy(default_route_entry)
        if not line:
            continue
        toks = line.split()
        flags = ['U']
        if toks[0] == "default":
            entry['destination'] = "0.0.0.0"
            entry['genmask'] = "0.0.0.0"
        else:
            if '/' in toks[0]:
                (addr, cidr) = toks[0].split("/")
            else:
                addr = toks[0]
                cidr = '32'
                flags.append("H")
                entry['genmask'] = net_prefix_to_ipv4_mask(cidr)
            entry['destination'] = addr
            entry['genmask'] = net_prefix_to_ipv4_mask(cidr)
            entry['gateway'] = "0.0.0.0"
        for i in range(len(toks)):
            if toks[i] == "via":
                entry['gateway'] = toks[i + 1]
                flags.insert(1, "G")
            if toks[i] == "dev":
                entry["iface"] = toks[i + 1]
            if toks[i] == "metric":
                entry['metric'] = toks[i + 1]
        entry['flags'] = ''.join(flags)
        routes['ipv4'].append(entry)
    try:
        (iproute_data6, _err6) = subp.subp(
            ["ip", "--oneline", "-6", "route", "list", "table", "all"],
            rcs=[0, 1])
    except subp.ProcessExecutionError:
        pass
    else:
        entries6 = iproute_data6.splitlines()
        for line in entries6:
            entry = {}
            if not line:
                continue
            toks = line.split()
            if toks[0] == "default":
                entry['destination'] = "::/0"
                entry['flags'] = "UG"
            else:
                entry['destination'] = toks[0]
                entry['gateway'] = "::"
                entry['flags'] = "U"
            for i in range(len(toks)):
                if toks[i] == "via":
                    entry['gateway'] = toks[i + 1]
                    entry['flags'] = "UG"
                if toks[i] == "dev":
                    entry["iface"] = toks[i + 1]
                if toks[i] == "metric":
                    entry['metric'] = toks[i + 1]
                if toks[i] == "expires":
                    entry['flags'] = entry['flags'] + 'e'
            routes['ipv6'].append(entry)
    return routes


def _netdev_route_info_netstat(route_data):
    routes = {}
    routes['ipv4'] = []
    routes['ipv6'] = []

    entries = route_data.splitlines()
    for line in entries:
        if not line:
            continue
        toks = line.split()
        # FreeBSD shows 6 items in the routing table:
        #  Destination  Gateway    Flags Refs    Use  Netif Expire
        #  default      10.65.0.1  UGS      0  34920 vtnet0
        #
        # Linux netstat shows 2 more:
        #  Destination  Gateway    Genmask  Flags Metric Ref    Use Iface
        #  0.0.0.0      10.65.0.1  0.0.0.0  UG    0      0        0 eth0
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
        (route_data6, _err6) = subp.subp(
            ["netstat", "-A", "inet6", "--route", "--numeric"], rcs=[0, 1])
    except subp.ProcessExecutionError:
        pass
    else:
        entries6 = route_data6.splitlines()
        for line in entries6:
            if not line:
                continue
            toks = line.split()
            if (len(toks) < 7 or toks[0] == "Kernel" or
                    toks[0] == "Destination" or toks[0] == "Internet" or
                    toks[0] == "Proto" or toks[0] == "Active"):
                continue
            entry = {
                'destination': toks[0],
                'gateway': toks[1],
                'flags': toks[2],
                'metric': toks[3],
                'ref': toks[4],
                'use': toks[5],
                'iface': toks[6],
            }
            # skip lo interface on ipv6
            if entry['iface'] == "lo":
                continue
            # strip /128 from address if it's included
            if entry['destination'].endswith('/128'):
                entry['destination'] = re.sub(
                    r'\/128$', '', entry['destination'])
            routes['ipv6'].append(entry)
    return routes


def route_info():
    routes = {}
    if subp.which('ip'):
        # Try iproute first of all
        (iproute_out, _err) = subp.subp(["ip", "-o", "route", "list"])
        routes = _netdev_route_info_iproute(iproute_out)
    elif subp.which('netstat'):
        # Fall back to net-tools if iproute2 is not present
        (route_out, _err) = subp.subp(
            ["netstat", "--route", "--numeric", "--extend"], rcs=[0, 1])
        routes = _netdev_route_info_netstat(route_out)
    else:
        LOG.warning(
            "Could not print routes: missing 'ip' and 'netstat' commands")
    return routes


def netdev_pformat():
    lines = []
    empty = "."
    try:
        netdev = netdev_info(empty=empty)
    except Exception as e:
        lines.append(
            util.center(
                "Net device info failed ({error})".format(error=str(e)),
                '!', 80))
    else:
        if not netdev:
            return '\n'
        fields = ['Device', 'Up', 'Address', 'Mask', 'Scope', 'Hw-Address']
        tbl = SimpleTable(fields)
        for (dev, data) in sorted(netdev.items()):
            for addr in data.get('ipv4'):
                tbl.add_row(
                    (dev, data["up"], addr["ip"], addr["mask"],
                     addr.get('scope', empty), data["hwaddr"]))
            for addr in data.get('ipv6'):
                tbl.add_row(
                    (dev, data["up"], addr["ip"], empty,
                     addr.get("scope6", empty), data["hwaddr"]))
            if len(data.get('ipv6')) + len(data.get('ipv4')) == 0:
                tbl.add_row((dev, data["up"], empty, empty, empty,
                             data["hwaddr"]))
        netdev_s = tbl.get_string()
        max_len = len(max(netdev_s.splitlines(), key=len))
        header = util.center("Net device info", "+", max_len)
        lines.extend([header, netdev_s])
    return "\n".join(lines) + "\n"


def route_pformat():
    lines = []
    try:
        routes = route_info()
    except Exception as e:
        lines.append(
            util.center(
                'Route info failed ({error})'.format(error=str(e)),
                '!', 80))
        util.logexc(LOG, "Route info failed: %s" % e)
    else:
        if routes.get('ipv4'):
            fields_v4 = ['Route', 'Destination', 'Gateway',
                         'Genmask', 'Interface', 'Flags']
            tbl_v4 = SimpleTable(fields_v4)
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
            fields_v6 = ['Route', 'Destination', 'Gateway', 'Interface',
                         'Flags']
            tbl_v6 = SimpleTable(fields_v6)
            for (n, r) in enumerate(routes.get('ipv6')):
                route_id = str(n)
                if r['iface'] == 'lo':
                    continue
                tbl_v6.add_row([route_id, r['destination'],
                                r.get('gateway', 'undefined'), r['iface'], r['flags']])
            route_s = tbl_v6.get_string()
            max_len = len(max(route_s.splitlines(), key=len))
            header = util.center("Route IPv6 info", "+", max_len)
            lines.extend([header, route_s])
    return "\n".join(lines) + "\n"


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
