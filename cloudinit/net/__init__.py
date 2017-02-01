# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import errno
import logging
import os
import re

from cloudinit import util

LOG = logging.getLogger(__name__)
SYS_CLASS_NET = "/sys/class/net/"
DEFAULT_PRIMARY_INTERFACE = 'eth0'


def sys_dev_path(devname, path=""):
    return SYS_CLASS_NET + devname + "/" + path


def read_sys_net(devname, path, translate=None,
                 on_enoent=None, on_keyerror=None,
                 on_einval=None):
    dev_path = sys_dev_path(devname, path)
    try:
        contents = util.load_file(dev_path)
    except (OSError, IOError) as e:
        e_errno = getattr(e, 'errno', None)
        if e_errno in (errno.ENOENT, errno.ENOTDIR):
            if on_enoent is not None:
                return on_enoent(e)
        if e_errno in (errno.EINVAL,):
            if on_einval is not None:
                return on_einval(e)
        raise
    contents = contents.strip()
    if translate is None:
        return contents
    try:
        return translate[contents]
    except KeyError as e:
        if on_keyerror is not None:
            return on_keyerror(e)
        else:
            LOG.debug("Found unexpected (not translatable) value"
                      " '%s' in '%s", contents, dev_path)
            raise


def read_sys_net_safe(iface, field, translate=None):
    def on_excp_false(e):
        return False
    return read_sys_net(iface, field,
                        on_keyerror=on_excp_false,
                        on_enoent=on_excp_false,
                        on_einval=on_excp_false,
                        translate=translate)


def read_sys_net_int(iface, field):
    val = read_sys_net_safe(iface, field)
    if val is False:
        return None
    try:
        return int(val)
    except TypeError:
        return None


def is_up(devname):
    # The linux kernel says to consider devices in 'unknown'
    # operstate as up for the purposes of network configuration. See
    # Documentation/networking/operstates.txt in the kernel source.
    translate = {'up': True, 'unknown': True, 'down': False}
    return read_sys_net_safe(devname, "operstate", translate=translate)


def is_wireless(devname):
    return os.path.exists(sys_dev_path(devname, "wireless"))


def is_connected(devname):
    # is_connected isn't really as simple as that.  2 is
    # 'physically connected'. 3 is 'not connected'. but a wlan interface will
    # always show 3.
    iflink = read_sys_net_safe(devname, "iflink")
    if iflink == "2":
        return True
    if not is_wireless(devname):
        return False
    LOG.debug("'%s' is wireless, basing 'connected' on carrier", devname)
    return read_sys_net_safe(devname, "carrier",
                             translate={'0': False, '1': True})


def is_physical(devname):
    return os.path.exists(sys_dev_path(devname, "device"))


def is_present(devname):
    return os.path.exists(sys_dev_path(devname))


def get_devicelist():
    return os.listdir(SYS_CLASS_NET)


class ParserError(Exception):
    """Raised when a parser has issue parsing a file/content."""


def is_disabled_cfg(cfg):
    if not cfg or not isinstance(cfg, dict):
        return False
    return cfg.get('config') == "disabled"


def generate_fallback_config():
    """Determine which attached net dev is most likely to have a connection and
       generate network state to run dhcp on that interface"""
    # get list of interfaces that could have connections
    invalid_interfaces = set(['lo'])
    potential_interfaces = set(get_devicelist())
    potential_interfaces = potential_interfaces.difference(invalid_interfaces)
    # sort into interfaces with carrier, interfaces which could have carrier,
    # and ignore interfaces that are definitely disconnected
    connected = []
    possibly_connected = []
    for interface in potential_interfaces:
        if interface.startswith("veth"):
            continue
        if os.path.exists(sys_dev_path(interface, "bridge")):
            # skip any bridges
            continue
        carrier = read_sys_net_int(interface, 'carrier')
        if carrier:
            connected.append(interface)
            continue
        # check if nic is dormant or down, as this may make a nick appear to
        # not have a carrier even though it could acquire one when brought
        # online by dhclient
        dormant = read_sys_net_int(interface, 'dormant')
        if dormant:
            possibly_connected.append(interface)
            continue
        operstate = read_sys_net_safe(interface, 'operstate')
        if operstate in ['dormant', 'down', 'lowerlayerdown', 'unknown']:
            possibly_connected.append(interface)
            continue

    # don't bother with interfaces that might not be connected if there are
    # some that definitely are
    if connected:
        potential_interfaces = connected
    else:
        potential_interfaces = possibly_connected

    # if eth0 exists use it above anything else, otherwise get the interface
    # that we can read 'first' (using the sorted defintion of first).
    names = list(sorted(potential_interfaces))
    if DEFAULT_PRIMARY_INTERFACE in names:
        names.remove(DEFAULT_PRIMARY_INTERFACE)
        names.insert(0, DEFAULT_PRIMARY_INTERFACE)
    target_name = None
    target_mac = None
    for name in names:
        mac = read_sys_net_safe(name, 'address')
        if mac:
            target_name = name
            target_mac = mac
            break
    if target_mac and target_name:
        nconf = {'config': [], 'version': 1}
        nconf['config'].append(
            {'type': 'physical', 'name': target_name,
             'mac_address': target_mac, 'subnets': [{'type': 'dhcp'}]})
        return nconf
    else:
        # can't read any interfaces addresses (or there are none); give up
        return None


def apply_network_config_names(netcfg, strict_present=True, strict_busy=True):
    """read the network config and rename devices accordingly.
    if strict_present is false, then do not raise exception if no devices
    match.  if strict_busy is false, then do not raise exception if the
    device cannot be renamed because it is currently configured."""
    renames = []
    for ent in netcfg.get('config', {}):
        if ent.get('type') != 'physical':
            continue
        mac = ent.get('mac_address')
        name = ent.get('name')
        if not mac:
            continue
        renames.append([mac, name])

    return _rename_interfaces(renames)


def _get_current_rename_info(check_downable=True):
    """Collect information necessary for rename_interfaces."""
    names = get_devicelist()
    bymac = {}
    for n in names:
        bymac[get_interface_mac(n)] = {
            'name': n, 'up': is_up(n), 'downable': None}

    if check_downable:
        nmatch = re.compile(r"[0-9]+:\s+(\w+)[@:]")
        ipv6, _err = util.subp(['ip', '-6', 'addr', 'show', 'permanent',
                                'scope', 'global'], capture=True)
        ipv4, _err = util.subp(['ip', '-4', 'addr', 'show'], capture=True)

        nics_with_addresses = set()
        for bytes_out in (ipv6, ipv4):
            nics_with_addresses.update(nmatch.findall(bytes_out))

        for d in bymac.values():
            d['downable'] = (d['up'] is False or
                             d['name'] not in nics_with_addresses)

    return bymac


def _rename_interfaces(renames, strict_present=True, strict_busy=True,
                       current_info=None):

    if not len(renames):
        LOG.debug("no interfaces to rename")
        return

    if current_info is None:
        current_info = _get_current_rename_info()

    cur_bymac = {}
    for mac, data in current_info.items():
        cur = data.copy()
        cur['mac'] = mac
        cur_bymac[mac] = cur

    def update_byname(bymac):
        return dict((data['name'], data)
                    for data in bymac.values())

    def rename(cur, new):
        util.subp(["ip", "link", "set", cur, "name", new], capture=True)

    def down(name):
        util.subp(["ip", "link", "set", name, "down"], capture=True)

    def up(name):
        util.subp(["ip", "link", "set", name, "up"], capture=True)

    ops = []
    errors = []
    ups = []
    cur_byname = update_byname(cur_bymac)
    tmpname_fmt = "cirename%d"
    tmpi = -1

    for mac, new_name in renames:
        cur = cur_bymac.get(mac, {})
        cur_name = cur.get('name')
        cur_ops = []
        if cur_name == new_name:
            # nothing to do
            continue

        if not cur_name:
            if strict_present:
                errors.append(
                    "[nic not present] Cannot rename mac=%s to %s"
                    ", not available." % (mac, new_name))
            continue

        if cur['up']:
            msg = "[busy] Error renaming mac=%s from %s to %s"
            if not cur['downable']:
                if strict_busy:
                    errors.append(msg % (mac, cur_name, new_name))
                continue
            cur['up'] = False
            cur_ops.append(("down", mac, new_name, (cur_name,)))
            ups.append(("up", mac, new_name, (new_name,)))

        if new_name in cur_byname:
            target = cur_byname[new_name]
            if target['up']:
                msg = "[busy-target] Error renaming mac=%s from %s to %s."
                if not target['downable']:
                    if strict_busy:
                        errors.append(msg % (mac, cur_name, new_name))
                    continue
                else:
                    cur_ops.append(("down", mac, new_name, (new_name,)))

            tmp_name = None
            while tmp_name is None or tmp_name in cur_byname:
                tmpi += 1
                tmp_name = tmpname_fmt % tmpi

            cur_ops.append(("rename", mac, new_name, (new_name, tmp_name)))
            target['name'] = tmp_name
            cur_byname = update_byname(cur_bymac)
            if target['up']:
                ups.append(("up", mac, new_name, (tmp_name,)))

        cur_ops.append(("rename", mac, new_name, (cur['name'], new_name)))
        cur['name'] = new_name
        cur_byname = update_byname(cur_bymac)
        ops += cur_ops

    opmap = {'rename': rename, 'down': down, 'up': up}

    if len(ops) + len(ups) == 0:
        if len(errors):
            LOG.debug("unable to do any work for renaming of %s", renames)
        else:
            LOG.debug("no work necessary for renaming of %s", renames)
    else:
        LOG.debug("achieving renaming of %s with ops %s", renames, ops + ups)

        for op, mac, new_name, params in ops + ups:
            try:
                opmap.get(op)(*params)
            except Exception as e:
                errors.append(
                    "[unknown] Error performing %s%s for %s, %s: %s" %
                    (op, params, mac, new_name, e))

    if len(errors):
        raise Exception('\n'.join(errors))


def get_interface_mac(ifname):
    """Returns the string value of an interface's MAC Address"""
    path = "address"
    if os.path.isdir(sys_dev_path(ifname, "bonding_slave")):
        # for a bond slave, get the nic's hwaddress, not the address it
        # is using because its part of a bond.
        path = "bonding_slave/perm_hwaddr"
    return read_sys_net_safe(ifname, path)


def get_interfaces_by_mac(devs=None):
    """Build a dictionary of tuples {mac: name}"""
    if devs is None:
        try:
            devs = get_devicelist()
        except OSError as e:
            if e.errno == errno.ENOENT:
                devs = []
            else:
                raise
    ret = {}
    for name in devs:
        mac = get_interface_mac(name)
        # some devices may not have a mac (tun0)
        if mac:
            ret[mac] = name
    return ret

# vi: ts=4 expandtab
