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

from cloudinit.net.network_state import mask_to_net_prefix
from cloudinit import util

LOG = logging.getLogger(__name__)
SYS_CLASS_NET = "/sys/class/net/"
DEFAULT_PRIMARY_INTERFACE = 'eth0'


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    """Sorting for Humans: natural sort order. Can be use as the key to sort
    functions.
    This will sort ['eth0', 'ens3', 'ens10', 'ens12', 'ens8', 'ens0'] as
    ['ens0', 'ens3', 'ens8', 'ens10', 'ens12', 'eth0'] instead of the simple
    python way which will produce ['ens0', 'ens10', 'ens12', 'ens3', 'ens8',
    'eth0']."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def get_sys_class_path():
    """Simple function to return the global SYS_CLASS_NET."""
    return SYS_CLASS_NET


def sys_dev_path(devname, path=""):
    return get_sys_class_path() + devname + "/" + path


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
    except ValueError:
        return None


def is_up(devname):
    # The linux kernel says to consider devices in 'unknown'
    # operstate as up for the purposes of network configuration. See
    # Documentation/networking/operstates.txt in the kernel source.
    translate = {'up': True, 'unknown': True, 'down': False}
    return read_sys_net_safe(devname, "operstate", translate=translate)


def is_wireless(devname):
    return os.path.exists(sys_dev_path(devname, "wireless"))


def is_bridge(devname):
    return os.path.exists(sys_dev_path(devname, "bridge"))


def is_bond(devname):
    return os.path.exists(sys_dev_path(devname, "bonding"))


def is_renamed(devname):
    """
    /* interface name assignment types (sysfs name_assign_type attribute) */
    #define NET_NAME_UNKNOWN	0	/* unknown origin (not exposed to user) */
    #define NET_NAME_ENUM		1	/* enumerated by kernel */
    #define NET_NAME_PREDICTABLE	2	/* predictably named by the kernel */
    #define NET_NAME_USER		3	/* provided by user-space */
    #define NET_NAME_RENAMED	4	/* renamed by user-space */
    """
    name_assign_type = read_sys_net_safe(devname, 'name_assign_type')
    if name_assign_type and name_assign_type in ['3', '4']:
        return True
    return False


def is_vlan(devname):
    uevent = str(read_sys_net_safe(devname, "uevent"))
    return 'DEVTYPE=vlan' in uevent.splitlines()


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


def device_driver(devname):
    """Return the device driver for net device named 'devname'."""
    driver = None
    driver_path = sys_dev_path(devname, "device/driver")
    # driver is a symlink to the driver *dir*
    if os.path.islink(driver_path):
        driver = os.path.basename(os.readlink(driver_path))

    return driver


def device_devid(devname):
    """Return the device id string for net device named 'devname'."""
    dev_id = read_sys_net_safe(devname, "device/device")
    if dev_id is False:
        return None

    return dev_id


def get_devicelist():
    try:
        devs = os.listdir(get_sys_class_path())
    except OSError as e:
        if e.errno == errno.ENOENT:
            devs = []
        else:
            raise
    return devs


class ParserError(Exception):
    """Raised when a parser has issue parsing a file/content."""


def is_disabled_cfg(cfg):
    if not cfg or not isinstance(cfg, dict):
        return False
    return cfg.get('config') == "disabled"


def find_fallback_nic(blacklist_drivers=None):
    """Return the name of the 'fallback' network device."""
    if not blacklist_drivers:
        blacklist_drivers = []

    if 'net.ifnames=0' in util.get_cmdline():
        LOG.debug('Stable ifnames disabled by net.ifnames=0 in /proc/cmdline')
    else:
        unstable = [device for device in get_devicelist()
                    if device != 'lo' and not is_renamed(device)]
        if len(unstable):
            LOG.debug('Found unstable nic names: %s; calling udevadm settle',
                      unstable)
            msg = 'Waiting for udev events to settle'
            util.log_time(LOG.debug, msg, func=util.udevadm_settle)

    # get list of interfaces that could have connections
    invalid_interfaces = set(['lo'])
    potential_interfaces = set([device for device in get_devicelist()
                                if device_driver(device) not in
                                blacklist_drivers])
    potential_interfaces = potential_interfaces.difference(invalid_interfaces)
    # sort into interfaces with carrier, interfaces which could have carrier,
    # and ignore interfaces that are definitely disconnected
    connected = []
    possibly_connected = []
    for interface in potential_interfaces:
        if interface.startswith("veth"):
            continue
        if is_bridge(interface):
            # skip any bridges
            continue
        if is_bond(interface):
            # skip any bonds
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
    names = list(sorted(potential_interfaces, key=natural_sort_key))
    if DEFAULT_PRIMARY_INTERFACE in names:
        names.remove(DEFAULT_PRIMARY_INTERFACE)
        names.insert(0, DEFAULT_PRIMARY_INTERFACE)

    # pick the first that has a mac-address
    for name in names:
        if read_sys_net_safe(name, 'address'):
            return name
    return None


def generate_fallback_config(blacklist_drivers=None, config_driver=None):
    """Determine which attached net dev is most likely to have a connection and
       generate network state to run dhcp on that interface"""

    if not config_driver:
        config_driver = False

    target_name = find_fallback_nic(blacklist_drivers=blacklist_drivers)
    if target_name:
        target_mac = read_sys_net_safe(target_name, 'address')
        nconf = {'config': [], 'version': 1}
        cfg = {'type': 'physical', 'name': target_name,
               'mac_address': target_mac, 'subnets': [{'type': 'dhcp'}]}
        # inject the device driver name, dev_id into config if enabled and
        # device has a valid device driver value
        if config_driver:
            driver = device_driver(target_name)
            if driver:
                cfg['params'] = {
                    'driver': driver,
                    'device_id': device_devid(target_name),
                }
        nconf['config'].append(cfg)
        return nconf
    else:
        # can't read any interfaces addresses (or there are none); give up
        return None


def apply_network_config_names(netcfg, strict_present=True, strict_busy=True):
    """read the network config and rename devices accordingly.
    if strict_present is false, then do not raise exception if no devices
    match.  if strict_busy is false, then do not raise exception if the
    device cannot be renamed because it is currently configured.

    renames are only attempted for interfaces of type 'physical'.  It is
    expected that the network system will create other devices with the
    correct name in place."""

    def _version_1(netcfg):
        renames = []
        for ent in netcfg.get('config', {}):
            if ent.get('type') != 'physical':
                continue
            mac = ent.get('mac_address')
            if not mac:
                continue
            name = ent.get('name')
            driver = ent.get('params', {}).get('driver')
            device_id = ent.get('params', {}).get('device_id')
            if not driver:
                driver = device_driver(name)
            if not device_id:
                device_id = device_devid(name)
            renames.append([mac, name, driver, device_id])
        return renames

    def _version_2(netcfg):
        renames = []
        for ent in netcfg.get('ethernets', {}).values():
            # only rename if configured to do so
            name = ent.get('set-name')
            if not name:
                continue
            # cloud-init requires macaddress for renaming
            mac = ent.get('match', {}).get('macaddress')
            if not mac:
                continue
            driver = ent.get('match', {}).get('driver')
            device_id = ent.get('match', {}).get('device_id')
            if not driver:
                driver = device_driver(name)
            if not device_id:
                device_id = device_devid(name)
            renames.append([mac, name, driver, device_id])
        return renames

    if netcfg.get('version') == 1:
        return _rename_interfaces(_version_1(netcfg))
    elif netcfg.get('version') == 2:
        return _rename_interfaces(_version_2(netcfg))

    raise RuntimeError('Failed to apply network config names. Found bad'
                       ' network config version: %s' % netcfg.get('version'))


def interface_has_own_mac(ifname, strict=False):
    """return True if the provided interface has its own address.

    Based on addr_assign_type in /sys.  Return true for any interface
    that does not have a 'stolen' address. Examples of such devices
    are bonds or vlans that inherit their mac from another device.
    Possible values are:
      0: permanent address    2: stolen from another device
      1: randomly generated   3: set using dev_set_mac_address"""

    assign_type = read_sys_net_int(ifname, "addr_assign_type")
    if assign_type is None:
        # None is returned if this nic had no 'addr_assign_type' entry.
        # if strict, raise an error, if not return True.
        if strict:
            raise ValueError("%s had no addr_assign_type.")
        return True
    return assign_type in (0, 1, 3)


def _get_current_rename_info(check_downable=True):
    """Collect information necessary for rename_interfaces.

    returns a dictionary by mac address like:
       {name:
         {
          'downable': None or boolean indicating that the
                      device has only automatically assigned ip addrs.
          'device_id': Device id value (if it has one)
          'driver': Device driver (if it has one)
          'mac': mac address (in lower case)
          'name': name
          'up': boolean: is_up(name)
         }}
    """
    cur_info = {}
    for (name, mac, driver, device_id) in get_interfaces():
        cur_info[name] = {
            'downable': None,
            'device_id': device_id,
            'driver': driver,
            'mac': mac.lower(),
            'name': name,
            'up': is_up(name),
        }

    if check_downable:
        nmatch = re.compile(r"[0-9]+:\s+(\w+)[@:]")
        ipv6, _err = util.subp(['ip', '-6', 'addr', 'show', 'permanent',
                                'scope', 'global'], capture=True)
        ipv4, _err = util.subp(['ip', '-4', 'addr', 'show'], capture=True)

        nics_with_addresses = set()
        for bytes_out in (ipv6, ipv4):
            nics_with_addresses.update(nmatch.findall(bytes_out))

        for d in cur_info.values():
            d['downable'] = (d['up'] is False or
                             d['name'] not in nics_with_addresses)

    return cur_info


def _rename_interfaces(renames, strict_present=True, strict_busy=True,
                       current_info=None):

    if not len(renames):
        LOG.debug("no interfaces to rename")
        return

    if current_info is None:
        current_info = _get_current_rename_info()

    cur_info = {}
    for name, data in current_info.items():
        cur = data.copy()
        if cur.get('mac'):
            cur['mac'] = cur['mac'].lower()
        cur['name'] = name
        cur_info[name] = cur

    def update_byname(bymac):
        return dict((data['name'], data)
                    for data in cur_info.values())

    def rename(cur, new):
        util.subp(["ip", "link", "set", cur, "name", new], capture=True)

    def down(name):
        util.subp(["ip", "link", "set", name, "down"], capture=True)

    def up(name):
        util.subp(["ip", "link", "set", name, "up"], capture=True)

    ops = []
    errors = []
    ups = []
    cur_byname = update_byname(cur_info)
    tmpname_fmt = "cirename%d"
    tmpi = -1

    def entry_match(data, mac, driver, device_id):
        """match if set and in data"""
        if mac and driver and device_id:
            return (data['mac'] == mac and
                    data['driver'] == driver and
                    data['device_id'] == device_id)
        elif mac and driver:
            return (data['mac'] == mac and
                    data['driver'] == driver)
        elif mac:
            return (data['mac'] == mac)

        return False

    def find_entry(mac, driver, device_id):
        match = [data for data in cur_info.values()
                 if entry_match(data, mac, driver, device_id)]
        if len(match):
            if len(match) > 1:
                msg = ('Failed to match a single device. Matched devices "%s"'
                       ' with search values "(mac:%s driver:%s device_id:%s)"'
                       % (match, mac, driver, device_id))
                raise ValueError(msg)
            return match[0]

        return None

    for mac, new_name, driver, device_id in renames:
        if mac:
            mac = mac.lower()
        cur_ops = []
        cur = find_entry(mac, driver, device_id)
        if not cur:
            if strict_present:
                errors.append(
                    "[nic not present] Cannot rename mac=%s to %s"
                    ", not available." % (mac, new_name))
            continue

        cur_name = cur.get('name')
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
            cur_byname = update_byname(cur_info)
            if target['up']:
                ups.append(("up", mac, new_name, (tmp_name,)))

        cur_ops.append(("rename", mac, new_name, (cur['name'], new_name)))
        cur['name'] = new_name
        cur_byname = update_byname(cur_info)
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


def get_interfaces_by_mac():
    """Build a dictionary of tuples {mac: name}.

    Bridges and any devices that have a 'stolen' mac are excluded."""
    ret = {}
    for name, mac, _driver, _devid in get_interfaces():
        if mac in ret:
            raise RuntimeError(
                "duplicate mac found! both '%s' and '%s' have mac '%s'" %
                (name, ret[mac], mac))
        ret[mac] = name
    return ret


def get_interfaces():
    """Return list of interface tuples (name, mac, driver, device_id)

    Bridges and any devices that have a 'stolen' mac are excluded."""
    ret = []
    devs = get_devicelist()
    empty_mac = '00:00:00:00:00:00'
    for name in devs:
        if not interface_has_own_mac(name):
            continue
        if is_bridge(name):
            continue
        if is_vlan(name):
            continue
        mac = get_interface_mac(name)
        # some devices may not have a mac (tun0)
        if not mac:
            continue
        if mac == empty_mac and name != 'lo':
            continue
        ret.append((name, mac, device_driver(name), device_devid(name)))
    return ret


class EphemeralIPv4Network(object):
    """Context manager which sets up temporary static network configuration.

    No operations are performed if the provided interface is already connected.
    If unconnected, bring up the interface with valid ip, prefix and broadcast.
    If router is provided setup a default route for that interface. Upon
    context exit, clean up the interface leaving no configuration behind.
    """

    def __init__(self, interface, ip, prefix_or_mask, broadcast, router=None):
        """Setup context manager and validate call signature.

        @param interface: Name of the network interface to bring up.
        @param ip: IP address to assign to the interface.
        @param prefix_or_mask: Either netmask of the format X.X.X.X or an int
            prefix.
        @param broadcast: Broadcast address for the IPv4 network.
        @param router: Optionally the default gateway IP.
        """
        if not all([interface, ip, prefix_or_mask, broadcast]):
            raise ValueError(
                'Cannot init network on {0} with {1}/{2} and bcast {3}'.format(
                    interface, ip, prefix_or_mask, broadcast))
        try:
            self.prefix = mask_to_net_prefix(prefix_or_mask)
        except ValueError as e:
            raise ValueError(
                'Cannot setup network: {0}'.format(e))
        self.interface = interface
        self.ip = ip
        self.broadcast = broadcast
        self.router = router
        self.cleanup_cmds = []  # List of commands to run to cleanup state.

    def __enter__(self):
        """Perform ephemeral network setup if interface is not connected."""
        self._bringup_device()
        if self.router:
            self._bringup_router()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown anything we set up."""
        for cmd in self.cleanup_cmds:
            util.subp(cmd, capture=True)

    def _delete_address(self, address, prefix):
        """Perform the ip command to remove the specified address."""
        util.subp(
            ['ip', '-family', 'inet', 'addr', 'del',
             '%s/%s' % (address, prefix), 'dev', self.interface],
            capture=True)

    def _bringup_device(self):
        """Perform the ip comands to fully setup the device."""
        cidr = '{0}/{1}'.format(self.ip, self.prefix)
        LOG.debug(
            'Attempting setup of ephemeral network on %s with %s brd %s',
            self.interface, cidr, self.broadcast)
        try:
            util.subp(
                ['ip', '-family', 'inet', 'addr', 'add', cidr, 'broadcast',
                 self.broadcast, 'dev', self.interface],
                capture=True, update_env={'LANG': 'C'})
        except util.ProcessExecutionError as e:
            if "File exists" not in e.stderr:
                raise
            LOG.debug(
                'Skip ephemeral network setup, %s already has address %s',
                self.interface, self.ip)
        else:
            # Address creation success, bring up device and queue cleanup
            util.subp(
                ['ip', '-family', 'inet', 'link', 'set', 'dev', self.interface,
                 'up'], capture=True)
            self.cleanup_cmds.append(
                ['ip', '-family', 'inet', 'link', 'set', 'dev', self.interface,
                 'down'])
            self.cleanup_cmds.append(
                ['ip', '-family', 'inet', 'addr', 'del', cidr, 'dev',
                 self.interface])

    def _bringup_router(self):
        """Perform the ip commands to fully setup the router if needed."""
        # Check if a default route exists and exit if it does
        out, _ = util.subp(['ip', 'route', 'show', '0.0.0.0/0'], capture=True)
        if 'default' in out:
            LOG.debug(
                'Skip ephemeral route setup. %s already has default route: %s',
                self.interface, out.strip())
            return
        util.subp(
            ['ip', '-4', 'route', 'add', 'default', 'via', self.router,
             'dev', self.interface], capture=True)
        self.cleanup_cmds.insert(
            0, ['ip', '-4', 'route', 'del', 'default', 'dev', self.interface])


class RendererNotFoundError(RuntimeError):
    pass


# vi: ts=4 expandtab
