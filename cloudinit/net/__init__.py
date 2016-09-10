#   Copyright (C) 2013-2014 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#   Author: Blake Rouse <blake.rouse@canonical.com>
#
#   Curtin is free software: you can redistribute it and/or modify it under
#   the terms of the GNU Affero General Public License as published by the
#   Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Curtin is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for
#   more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Curtin.  If not, see <http://www.gnu.org/licenses/>.

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


def read_sys_net(devname, path, translate=None, enoent=None, keyerror=None):
    try:
        contents = util.load_file(sys_dev_path(devname, path))
    except (OSError, IOError) as e:
        if getattr(e, 'errno', None) in (errno.ENOENT, errno.ENOTDIR):
            if enoent is not None:
                return enoent
        raise
    contents = contents.strip()
    if translate is None:
        return contents
    try:
        return translate.get(contents)
    except KeyError:
        LOG.debug("found unexpected value '%s' in '%s/%s'", contents,
                  devname, path)
        if keyerror is not None:
            return keyerror
        raise


def is_up(devname):
    # The linux kernel says to consider devices in 'unknown'
    # operstate as up for the purposes of network configuration. See
    # Documentation/networking/operstates.txt in the kernel source.
    translate = {'up': True, 'unknown': True, 'down': False}
    return read_sys_net(devname, "operstate", enoent=False, keyerror=False,
                        translate=translate)


def is_wireless(devname):
    return os.path.exists(sys_dev_path(devname, "wireless"))


def is_connected(devname):
    # is_connected isn't really as simple as that.  2 is
    # 'physically connected'. 3 is 'not connected'. but a wlan interface will
    # always show 3.
    try:
        iflink = read_sys_net(devname, "iflink", enoent=False)
        if iflink == "2":
            return True
        if not is_wireless(devname):
            return False
        LOG.debug("'%s' is wireless, basing 'connected' on carrier", devname)

        return read_sys_net(devname, "carrier", enoent=False, keyerror=False,
                            translate={'0': False, '1': True})

    except IOError as e:
        if e.errno == errno.EINVAL:
            return False
        raise


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


def sys_netdev_info(name, field):
    if not os.path.exists(os.path.join(SYS_CLASS_NET, name)):
        raise OSError("%s: interface does not exist in %s" %
                      (name, SYS_CLASS_NET))
    fname = os.path.join(SYS_CLASS_NET, name, field)
    if not os.path.exists(fname):
        raise OSError("%s: could not find sysfs entry: %s" % (name, fname))
    data = util.load_file(fname)
    if data[-1] == '\n':
        data = data[:-1]
    return data


def generate_fallback_config():
    """Determine which attached net dev is most likely to have a connection and
       generate network state to run dhcp on that interface"""
    # by default use eth0 as primary interface
    nconf = {'config': [], 'version': 1}

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
        try:
            carrier = int(sys_netdev_info(interface, 'carrier'))
            if carrier:
                connected.append(interface)
                continue
        except OSError:
            pass
        # check if nic is dormant or down, as this may make a nick appear to
        # not have a carrier even though it could acquire one when brought
        # online by dhclient
        try:
            dormant = int(sys_netdev_info(interface, 'dormant'))
            if dormant:
                possibly_connected.append(interface)
                continue
        except OSError:
            pass
        try:
            operstate = sys_netdev_info(interface, 'operstate')
            if operstate in ['dormant', 'down', 'lowerlayerdown', 'unknown']:
                possibly_connected.append(interface)
                continue
        except OSError:
            pass

    # don't bother with interfaces that might not be connected if there are
    # some that definitely are
    if connected:
        potential_interfaces = connected
    else:
        potential_interfaces = possibly_connected
    # if there are no interfaces, give up
    if not potential_interfaces:
        return
    # if eth0 exists use it above anything else, otherwise get the interface
    # that looks 'first'
    if DEFAULT_PRIMARY_INTERFACE in potential_interfaces:
        name = DEFAULT_PRIMARY_INTERFACE
    else:
        name = sorted(potential_interfaces)[0]

    mac = sys_netdev_info(name, 'address')
    target_name = name

    nconf['config'].append(
        {'type': 'physical', 'name': target_name,
         'mac_address': mac, 'subnets': [{'type': 'dhcp'}]})
    return nconf


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
    return read_sys_net(ifname, path, enoent=False)


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

# vi: ts=4 expandtab syntax=python
