# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import glob
import gzip
import io
import shlex
import sys

import six

from . import get_devicelist
from . import read_sys_net_safe

from cloudinit import util

PY26 = sys.version_info[0:2] == (2, 6)


def _shlex_split(blob):
    if PY26 and isinstance(blob, six.text_type):
        # Older versions don't support unicode input
        blob = blob.encode("utf8")
    return shlex.split(blob)


def _load_shell_content(content, add_empty=False, empty_val=None):
    """Given shell like syntax (key=value\nkey2=value2\n) in content
       return the data in dictionary form.  If 'add_empty' is True
       then add entries in to the returned dictionary for 'VAR='
       variables.  Set their value to empty_val."""
    data = {}
    for line in _shlex_split(content):
        key, value = line.split("=", 1)
        if not value:
            value = empty_val
        if add_empty or value:
            data[key] = value

    return data


def _klibc_to_config_entry(content, mac_addrs=None):
    """Convert a klibc written shell content file to a 'config' entry
    When ip= is seen on the kernel command line in debian initramfs
    and networking is brought up, ipconfig will populate
    /run/net-<name>.cfg.

    The files are shell style syntax, and examples are in the tests
    provided here.  There is no good documentation on this unfortunately.

    DEVICE=<name> is expected/required and PROTO should indicate if
    this is 'static' or 'dhcp' or 'dhcp6' (LP: #1621507).
    note that IPV6PROTO is also written by newer code to address the
    possibility of both ipv4 and ipv6 getting addresses.
    """

    if mac_addrs is None:
        mac_addrs = {}

    data = _load_shell_content(content)
    try:
        name = data['DEVICE'] if 'DEVICE' in data else data['DEVICE6']
    except KeyError:
        raise ValueError("no 'DEVICE' or 'DEVICE6' entry in data")

    # ipconfig on precise does not write PROTO
    # IPv6 config gives us IPV6PROTO, not PROTO.
    proto = data.get('PROTO', data.get('IPV6PROTO'))
    if not proto:
        if data.get('filename'):
            proto = 'dhcp'
        else:
            proto = 'static'

    if proto not in ('static', 'dhcp', 'dhcp6'):
        raise ValueError("Unexpected value for PROTO: %s" % proto)

    iface = {
        'type': 'physical',
        'name': name,
        'subnets': [],
    }

    if name in mac_addrs:
        iface['mac_address'] = mac_addrs[name]

    # Handle both IPv4 and IPv6 values
    for v, pre in (('ipv4', 'IPV4'), ('ipv6', 'IPV6')):
        # if no IPV4ADDR or IPV6ADDR, then go on.
        if pre + "ADDR" not in data:
            continue

        # PROTO for ipv4, IPV6PROTO for ipv6
        cur_proto = data.get(pre + 'PROTO', proto)
        subnet = {'type': cur_proto, 'control': 'manual'}

        # these fields go right on the subnet
        for key in ('NETMASK', 'BROADCAST', 'GATEWAY'):
            if pre + key in data:
                subnet[key.lower()] = data[pre + key]

        dns = []
        # handle IPV4DNS0 or IPV6DNS0
        for nskey in ('DNS0', 'DNS1'):
            ns = data.get(pre + nskey)
            # verify it has something other than 0.0.0.0 (or ipv6)
            if ns and len(ns.strip(":.0")):
                dns.append(data[pre + nskey])
        if dns:
            subnet['dns_nameservers'] = dns
            # add search to both ipv4 and ipv6, as it has no namespace
            search = data.get('DOMAINSEARCH')
            if search:
                if ',' in search:
                    subnet['dns_search'] = search.split(",")
                else:
                    subnet['dns_search'] = search.split()

        iface['subnets'].append(subnet)

    return name, iface


def config_from_klibc_net_cfg(files=None, mac_addrs=None):
    if files is None:
        files = glob.glob('/run/net-*.conf') + glob.glob('/run/net6-*.conf')

    entries = []
    names = {}
    for cfg_file in files:
        name, entry = _klibc_to_config_entry(util.load_file(cfg_file),
                                             mac_addrs=mac_addrs)
        if name in names:
            prev = names[name]['entry']
            if prev.get('mac_address') != entry.get('mac_address'):
                raise ValueError(
                    "device '%s' was defined multiple times (%s)"
                    " but had differing mac addresses: %s -> %s.",
                    (name, ' '.join(names[name]['files']),
                     prev.get('mac_address'), entry.get('mac_address')))
            prev['subnets'].extend(entry['subnets'])
            names[name]['files'].append(cfg_file)
        else:
            names[name] = {'files': [cfg_file], 'entry': entry}
            entries.append(entry)

    return {'config': entries, 'version': 1}


def _decomp_gzip(blob, strict=True):
    # decompress blob. raise exception if not compressed unless strict=False.
    with io.BytesIO(blob) as iobuf:
        gzfp = None
        try:
            gzfp = gzip.GzipFile(mode="rb", fileobj=iobuf)
            return gzfp.read()
        except IOError:
            if strict:
                raise
            return blob
        finally:
            if gzfp:
                gzfp.close()


def _b64dgz(b64str, gzipped="try"):
    # decode a base64 string.  If gzipped is true, transparently uncompresss
    # if gzipped is 'try', then try gunzip, returning the original on fail.
    try:
        blob = base64.b64decode(b64str)
    except TypeError:
        raise ValueError("Invalid base64 text: %s" % b64str)

    if not gzipped:
        return blob

    return _decomp_gzip(blob, strict=gzipped != "try")


def read_kernel_cmdline_config(files=None, mac_addrs=None, cmdline=None):
    if cmdline is None:
        cmdline = util.get_cmdline()

    if 'network-config=' in cmdline:
        data64 = None
        for tok in cmdline.split():
            if tok.startswith("network-config="):
                data64 = tok.split("=", 1)[1]
        if data64:
            return util.load_yaml(_b64dgz(data64))

    if 'ip=' not in cmdline and 'ip6=' not in cmdline:
        return None

    if mac_addrs is None:
        mac_addrs = {}
        for k in get_devicelist():
            mac_addr = read_sys_net_safe(k, 'address')
            if mac_addr:
                mac_addrs[k] = mac_addr

    return config_from_klibc_net_cfg(files=files, mac_addrs=mac_addrs)

# vi: ts=4 expandtab
