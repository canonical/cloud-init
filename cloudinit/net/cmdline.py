# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
import base64
import glob
import gzip
import io
import logging
import os

from cloudinit import util

from . import get_devicelist
from . import read_sys_net_safe

_OPEN_ISCSI_INTERFACE_FILE = "/run/initramfs/open-iscsi.interface"

KERNEL_CMDLINE_NETWORK_CONFIG_DISABLED = "disabled"


class InitramfsNetworkConfigSource(metaclass=abc.ABCMeta):
    """ABC for net config sources that read config written by initramfses"""

    @abc.abstractmethod
    def is_applicable(self):
        # type: () -> bool
        """Is this initramfs config source applicable to the current system?"""
        pass

    @abc.abstractmethod
    def render_config(self):
        # type: () -> dict
        """Render a v1 or v2 network config from the initramfs configuration"""
        pass


class KlibcNetworkConfigSource(InitramfsNetworkConfigSource):
    """InitramfsNetworkConfigSource for klibc initramfs (i.e. Debian/Ubuntu)

    Has three parameters, but they are intended to make testing simpler, _not_
    for use in production code.  (This is indicated by the prepended
    underscores.)
    """

    def __init__(self, _files=None, _mac_addrs=None, _cmdline=None):
        self._files = _files
        self._mac_addrs = _mac_addrs
        self._cmdline = _cmdline

        # Set defaults here, as they require computation that we don't want to
        # do at method definition time
        if self._files is None:
            self._files = _get_klibc_net_cfg_files()
        if self._cmdline is None:
            self._cmdline = util.get_cmdline()
        if self._mac_addrs is None:
            self._mac_addrs = {}
            for k in get_devicelist():
                mac_addr = read_sys_net_safe(k, 'address')
                if mac_addr:
                    self._mac_addrs[k] = mac_addr

    def is_applicable(self):
        # type: () -> bool
        """
        Return whether this system has klibc initramfs network config or not

        Will return True if:
            (a) klibc files exist in /run, AND
            (b) either:
                (i) ip= or ip6= are on the kernel cmdline, OR
                (ii) an open-iscsi interface file is present in the system
        """
        if self._files:
            if 'ip=' in self._cmdline or 'ip6=' in self._cmdline:
                return True
            if os.path.exists(_OPEN_ISCSI_INTERFACE_FILE):
                # iBft can configure networking without ip=
                return True
        return False

    def render_config(self):
        # type: () -> dict
        return config_from_klibc_net_cfg(
            files=self._files, mac_addrs=self._mac_addrs,
        )


class NetplanConfigSource(InitramfsNetworkConfigSource):
    """InitramfsNetworkConfigSource for netplan initramfs. """

    def __init__(self, _files=None):
        self._files = _files

        # Set defaults here, as they require computation that we don't want to
        # do at method definition time
        if self._files is None:
            self._files = _get_netplan_net_cfg_files()

    def is_applicable(self):
        # type: () -> bool
        """
        Return whether this system has netplan initramfs network config or not

        Will return True if one or more netplan files exist in
        /run/netplan/*.yaml
        """
        if len(self._files):
                return True
        return False

    def render_config(self):
        # type: () -> dict
        return config_from_netplan_net_cfg(files=self._files)


_INITRAMFS_CONFIG_SOURCES = [NetplanConfigSource, KlibcNetworkConfigSource]


def _klibc_to_config_entry(content, mac_addrs=None):
    """Convert a klibc written shell content file to a 'config' entry
    When ip= is seen on the kernel command line in debian initramfs
    and networking is brought up, ipconfig will populate
    /run/net-<name>.cfg.

    The files are shell style syntax, and examples are in the tests
    provided here.  There is no good documentation on this unfortunately.

    DEVICE=<name> is expected/required and PROTO should indicate if
    this is 'none' (static) or 'dhcp' or 'dhcp6' (LP: #1621507).
    note that IPV6PROTO is also written by newer code to address the
    possibility of both ipv4 and ipv6 getting addresses.

    if DEVICE contains a '.' this indicates it is a VLAN device and
    we must return config for the base device and vlan layer.

    Full syntax is documented at:
    https://git.kernel.org/pub/scm/libs/klibc/klibc.git/plain/usr/kinit/ipconfig/README.ipconfig
    """

    if mac_addrs is None:
        mac_addrs = {}

    data = util.load_shell_content(content)
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
            proto = 'none'

    if proto not in ('none', 'dhcp', 'dhcp6'):
        raise ValueError("Unexpected value for PROTO: %s" % proto)

    entries = []
    iface = {
        'type': 'physical',
        'name': name,
        'subnets': [],
    }

    if name in mac_addrs:
        iface['mac_address'] = mac_addrs[name]

    # handle a vlan link interface first
    if '.' in name:
        link_name, vlan_id = name.split('.')
        # update iface attributes for vlan type
        iface['type'] = 'vlan'
        iface['vlan_id'] = vlan_id
        iface['vlan_link'] = link_name
        link_iface = {
            'type': 'physical', 'name': link_name,
            'subnets': [{'type': 'static', 'control': 'manual'}],
        }
        if link_name in mac_addrs:
            link_iface['mac_address'] = mac_addrs[link_name]

        entries.append((link_name, link_iface))

    # Handle both IPv4 and IPv6 values
    for pre in ('IPV4', 'IPV6'):
        # if no IPV4ADDR or IPV6ADDR, then go on.
        if pre + "ADDR" not in data:
            continue

        # PROTO for ipv4, IPV6PROTO for ipv6
        cur_proto = data.get(pre + 'PROTO', proto)
        # ipconfig's 'none' is called 'static'
        if cur_proto == 'none':
            cur_proto = 'static'
        subnet = {'type': cur_proto, 'control': 'manual'}

        # only populate address for static types. While the rendered config
        # may have an address for dhcp, that is not really expected.
        if cur_proto == 'static':
            subnet['address'] = data[pre + 'ADDR']

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
    entries.append((name, iface))

    return entries


def _get_klibc_net_cfg_files():
    return glob.glob('/run/net-*.conf') + glob.glob('/run/net6-*.conf')


def config_from_klibc_net_cfg(files=None, mac_addrs=None):
    if files is None:
        files = _get_klibc_net_cfg_files()

    entries = []
    names = {}
    for cfg_file in files:
        parsed = _klibc_to_config_entry(util.load_file(cfg_file),
                                             mac_addrs=mac_addrs)
        for (name, entry) in parsed:
            if name in names:
                prev = names[name]['entry']
                if prev.get('mac_address') != entry.get('mac_address'):
                    raise ValueError(
                        "device '{name}' was defined multiple times ({files})"
                        " but had differing mac addresses: {old} -> {new}.".format(
                            name=name, files=' '.join(names[name]['files']),
                            old=prev.get('mac_address'),
                            new=entry.get('mac_address')))
                prev['subnets'].extend(entry['subnets'])
                names[name]['files'].append(cfg_file)
            else:
                names[name] = {'files': [cfg_file], 'entry': entry}
                entries.append(entry)

    return {'config': entries, 'version': 1}


def _get_netplan_net_cfg_files():
    return sorted(glob.glob('/run/netplan/*.yaml'))


def config_from_netplan_net_cfg(files=None):
    if files is None:
        files = _get_netplan_net_cfg_files()

    configs = []
    for cfg_file in files:
        configs.append(util.read_conf(cfg_file))
        util.del_file(cfg_file)

    return util.mergemanydict(configs).get('network', {})


def read_initramfs_config():
    """
    Return v1 network config for initramfs-configured networking (or None)

    This will consider each _INITRAMFS_CONFIG_SOURCES entry in turn, and return
    v1 or v2 network configuration for the first one that is applicable.
    If none are applicable, return None.
    """
    for src_cls in _INITRAMFS_CONFIG_SOURCES:
        cfg_source = src_cls()

        if not cfg_source.is_applicable():
            continue

        return cfg_source.render_config()
    return None


def _decomp_gzip(blob):
    # decompress blob or return original blob
    with io.BytesIO(blob) as iobuf:
        gzfp = None
        try:
            gzfp = gzip.GzipFile(mode="rb", fileobj=iobuf)
            return gzfp.read()
        except IOError:
            return blob
        finally:
            if gzfp:
                gzfp.close()


def _b64dgz(data):
    """Decode a string base64 encoding, if gzipped, uncompress as well

    :return: decompressed unencoded string of the data or empty string on
       unencoded data.
    """
    try:
        blob = base64.b64decode(data)
    except (TypeError, ValueError):
        logging.error(
            "Expected base64 encoded kernel commandline parameter"
            " network-config. Ignoring network-config=%s.", data)
        return ''

    return _decomp_gzip(blob)


def read_kernel_cmdline_config(cmdline=None):
    if cmdline is None:
        cmdline = util.get_cmdline()

    if 'network-config=' in cmdline:
        data64 = None
        for tok in cmdline.split():
            if tok.startswith("network-config="):
                data64 = tok.split("=", 1)[1]
        if data64:
            if data64 == KERNEL_CMDLINE_NETWORK_CONFIG_DISABLED:
                return {"config": "disabled"}
            return util.load_yaml(_b64dgz(data64))

    return None

# vi: ts=4 expandtab
