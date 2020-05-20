# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import errno
import ipaddress
import logging
import os
import re
from functools import partial

from cloudinit import util
from cloudinit.net.network_state import mask_to_net_prefix
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)


class ParserError(Exception):
    """Raised when a parser has issue parsing a file/content."""


def is_disabled_cfg(cfg):
    if not cfg or not isinstance(cfg, dict):
        return False
    return cfg.get('config') == "disabled"





def wait_for_physdevs(netcfg, strict=True):
    physdevs = extract_physdevs(netcfg)

    # set of expected iface names and mac addrs
    expected_ifaces = dict([(iface[0], iface[1]) for iface in physdevs])
    expected_macs = set(expected_ifaces.keys())

    # set of current macs
    present_macs = get_interfaces_by_mac().keys()

    # compare the set of expected mac address values to
    # the current macs present; we only check MAC as cloud-init
    # has not yet renamed interfaces and the netcfg may include
    # such renames.
    for _ in range(0, 5):
        if expected_macs.issubset(present_macs):
            LOG.debug('net: all expected physical devices present')
            return

        missing = expected_macs.difference(present_macs)
        LOG.debug('net: waiting for expected net devices: %s', missing)
        for mac in missing:
            # trigger a settle, unless this interface exists
            syspath = sys_dev_path(expected_ifaces[mac])
            settle = partial(util.udevadm_settle, exists=syspath)
            msg = 'Waiting for udev events to settle or %s exists' % syspath
            util.log_time(LOG.debug, msg, func=settle)

        # update present_macs after settles
        present_macs = get_interfaces_by_mac().keys()

    msg = 'Not all expected physical devices present: %s' % missing
    LOG.warning(msg)
    if strict:
        raise RuntimeError(msg)


def apply_network_config_names(netcfg, strict_present=True, strict_busy=True):
    """read the network config and rename devices accordingly.
    if strict_present is false, then do not raise exception if no devices
    match.  if strict_busy is false, then do not raise exception if the
    device cannot be renamed because it is currently configured.

    renames are only attempted for interfaces of type 'physical'.  It is
    expected that the network system will create other devices with the
    correct name in place."""

    try:
        _rename_interfaces(extract_physdevs(netcfg))
    except RuntimeError as e:
        raise RuntimeError('Failed to apply network config names: %s' % e)


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


def get_ib_interface_hwaddr(ifname, ethernet_format):
    """Returns the string value of an Infiniband interface's hardware
    address. If ethernet_format is True, an Ethernet MAC-style 6 byte
    representation of the address will be returned.
    """
    # Type 32 is Infiniband.
    if read_sys_net_safe(ifname, 'type') == '32':
        mac = get_interface_mac(ifname)
        if mac and ethernet_format:
            # Use bytes 13-15 and 18-20 of the hardware address.
            mac = mac[36:-14] + mac[51:]
        return mac


def get_interfaces_by_mac():
    if util.is_FreeBSD():
        return get_interfaces_by_mac_on_freebsd()
    elif util.is_NetBSD():
        return get_interfaces_by_mac_on_netbsd()
    elif util.is_OpenBSD():
        return get_interfaces_by_mac_on_openbsd()
    else:
        return get_interfaces_by_mac_on_linux()


def get_interfaces_by_mac_on_freebsd():
    (out, _) = util.subp(['ifconfig', '-a', 'ether'])

    # flatten each interface block in a single line
    def flatten(out):
        curr_block = ''
        for l in out.split('\n'):
            if l.startswith('\t'):
                curr_block += l
            else:
                if curr_block:
                    yield curr_block
                curr_block = l
        yield curr_block

    # looks for interface and mac in a list of flatten block
    def find_mac(flat_list):
        for block in flat_list:
            m = re.search(
                r"^(?P<ifname>\S*): .*ether\s(?P<mac>[\da-f:]{17}).*",
                block)
            if m:
                yield (m.group('mac'), m.group('ifname'))
    results = {mac: ifname for mac, ifname in find_mac(flatten(out))}
    return results


def get_interfaces_by_mac_on_netbsd():
    ret = {}
    re_field_match = (
            r"(?P<ifname>\w+).*address:\s"
            r"(?P<mac>([\da-f]{2}[:-]){5}([\da-f]{2})).*")
    (out, _) = util.subp(['ifconfig', '-a'])
    if_lines = re.sub(r'\n\s+', ' ', out).splitlines()
    for line in if_lines:
        m = re.match(re_field_match, line)
        if m:
            fields = m.groupdict()
            ret[fields['mac']] = fields['ifname']
    return ret


def get_interfaces_by_mac_on_openbsd():
    ret = {}
    re_field_match = (
        r"(?P<ifname>\w+).*lladdr\s"
        r"(?P<mac>([\da-f]{2}[:-]){5}([\da-f]{2})).*")
    (out, _) = util.subp(['ifconfig', '-a'])
    if_lines = re.sub(r'\n\s+', ' ', out).splitlines()
    for line in if_lines:
        m = re.match(re_field_match, line)
        if m:
            fields = m.groupdict()
            ret[fields['mac']] = fields['ifname']
    return ret


def get_interfaces_by_mac_on_linux():
    """Build a dictionary of tuples {mac: name}.

    Bridges and any devices that have a 'stolen' mac are excluded."""
    ret = {}
    for name, mac, _driver, _devid in get_interfaces():
        if mac in ret:
            raise RuntimeError(
                "duplicate mac found! both '%s' and '%s' have mac '%s'" %
                (name, ret[mac], mac))
        ret[mac] = name
        # Try to get an Infiniband hardware address (in 6 byte Ethernet format)
        # for the interface.
        ib_mac = get_ib_interface_hwaddr(name, True)
        if ib_mac:
            if ib_mac in ret:
                raise RuntimeError(
                    "duplicate mac found! both '%s' and '%s' have mac '%s'" %
                    (name, ret[ib_mac], ib_mac))
            ret[ib_mac] = name
    return ret


def get_interfaces():
    """Return list of interface tuples (name, mac, driver, device_id)

    Bridges and any devices that have a 'stolen' mac are excluded."""
    ret = []
    devs = get_devicelist()
    # 16 somewhat arbitrarily chosen.  Normally a mac is 6 '00:' tokens.
    zero_mac = ':'.join(('00',) * 16)
    for name in devs:
        if not interface_has_own_mac(name):
            continue
        if is_bridge(name):
            continue
        if is_vlan(name):
            continue
        if is_bond(name):
            continue
        if get_master(name) is not None and not master_is_bridge_or_bond(name):
            continue
        if is_netfailover(name):
            continue
        mac = get_interface_mac(name)
        # some devices may not have a mac (tun0)
        if not mac:
            continue
        # skip nics that have no mac (00:00....)
        if name != 'lo' and mac == zero_mac[:len(mac)]:
            continue
        ret.append((name, mac, device_driver(name), device_devid(name)))
    return ret


def get_ib_hwaddrs_by_interface():
    """Build a dictionary mapping Infiniband interface names to their hardware
    address."""
    ret = {}
    for name, _, _, _ in get_interfaces():
        ib_mac = get_ib_interface_hwaddr(name, False)
        if ib_mac:
            if ib_mac in ret:
                raise RuntimeError(
                    "duplicate mac found! both '%s' and '%s' have mac '%s'" %
                    (name, ret[ib_mac], ib_mac))
            ret[name] = ib_mac
    return ret


def has_url_connectivity(url):
    """Return true when the instance has access to the provided URL

    Logs a warning if url is not the expected format.
    """
    if not any([url.startswith('http://'), url.startswith('https://')]):
        LOG.warning(
            "Ignoring connectivity check. Expected URL beginning with http*://"
            " received '%s'", url)
        return False
    try:
        readurl(url, timeout=5)
    except UrlError:
        return False
    return True


def is_ip_address(s: str) -> bool:
    """Returns a bool indicating if ``s`` is an IP address.

    :param s:
        The string to test.

    :return:
        A bool indicating if the string contains an IP address or not.
    """
    try:
        ipaddress.ip_address(s)
    except ValueError:
        return False
    return True


def is_ipv4_address(s: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv4 address.

    :param s:
        The string to test.

    :return:
        A bool indicating if the string contains an IPv4 address or not.
    """
    try:
        ipaddress.IPv4Address(s)
    except ValueError:
        return False
    return True


class EphemeralIPv4Network(object):
    """Context manager which sets up temporary static network configuration.

    No operations are performed if the provided interface already has the
    specified configuration.
    This can be verified with the connectivity_url.
    If unconnected, bring up the interface with valid ip, prefix and broadcast.
    If router is provided setup a default route for that interface. Upon
    context exit, clean up the interface leaving no configuration behind.
    """

    def __init__(self, interface, ip, prefix_or_mask, broadcast, router=None,
                 connectivity_url=None, static_routes=None):
        """Setup context manager and validate call signature.

        @param interface: Name of the network interface to bring up.
        @param ip: IP address to assign to the interface.
        @param prefix_or_mask: Either netmask of the format X.X.X.X or an int
            prefix.
        @param broadcast: Broadcast address for the IPv4 network.
        @param router: Optionally the default gateway IP.
        @param connectivity_url: Optionally, a URL to verify if a usable
           connection already exists.
        @param static_routes: Optionally a list of static routes from DHCP
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

        self.connectivity_url = connectivity_url
        self.interface = interface
        self.ip = ip
        self.broadcast = broadcast
        self.router = router
        self.static_routes = static_routes
        self.cleanup_cmds = []  # List of commands to run to cleanup state.

    def __enter__(self):
        """Perform ephemeral network setup if interface is not connected."""
        if self.connectivity_url:
            if has_url_connectivity(self.connectivity_url):
                LOG.debug(
                    'Skip ephemeral network setup, instance has connectivity'
                    ' to %s', self.connectivity_url)
                return

        self._bringup_device()

        # rfc3442 requires us to ignore the router config *if* classless static
        # routes are provided.
        #
        # https://tools.ietf.org/html/rfc3442
        #
        # If the DHCP server returns both a Classless Static Routes option and
        # a Router option, the DHCP client MUST ignore the Router option.
        #
        # Similarly, if the DHCP server returns both a Classless Static Routes
        # option and a Static Routes option, the DHCP client MUST ignore the
        # Static Routes option.
        if self.static_routes:
            self._bringup_static_routes()
        elif self.router:
            self._bringup_router()

    def __exit__(self, excp_type, excp_value, excp_traceback):
        """Teardown anything we set up."""
        for cmd in self.cleanup_cmds:
            util.subp(cmd, capture=True)

    def __delete_address_on_linux(self, cidr):
        """Perform the ip command to remove the specified address."""
        util.subp(['ip', '-family', 'inet', 'addr', 'del', cidr, 'dev',
                  self.interface], capture=True)

    def __delete_address_on_bsd(self, cidr):
        """Perform the ifconfig command to remove the specified address."""
        util.subp(['ifconfig', self.interface, 'inet', cidr, 'broadcast',
                  self.broadcast, 'delete'], capture=True)

    def _delete_address(self, address, prefix):
        """Perform the command to remove the specified address."""
        cidr = '{0}/{1}'.format(address, prefix)
        if util.is_BSD():
            self.__delete_address_on_bsd(cidr)
        else:
            self.__delete_address_on_linux(cidr)

    def __bringup_device_on_bsd(self):
        """Perform the ifconfig commands to fully setup the device"""
        cidr = '{0}/{1}'.format(self.ip, self.prefix)
        LOG.debug(
            'Attempting setup of ephemeral network on %s with %s brd %s',
            self.interface, cidr, self.broadcast)
        try:
            util.subp(
                ['ifconfig', self.interface, 'inet', cidr, 'broadcast',
                 self.broadcast],
                capture=True, update_env={'LANG': 'C'})
        except util.ProcessExecutionError as e:
            if "File exists" not in e.stderr:
                raise
            LOG.debug(
                'Skip ephemeral network setup, %s already has address %s',
                self.interface, self.ip)
        else:
            # Address creation success, setup queue cleanup
            self.cleanup_cmds.append(
                ['ifconfig', self.interface, 'inet', cidr, 'broadcast',
                 self.broadcast, 'delete'])
            self.cleanup_cmds.append(
                ['ifconfig', self.interface, 'inet', cidr, 'broadcast',
                 self.broadcast, 'down'])

    def __bringup_device_on_linux(self):
        """Perform the ip commands to fully setup the device."""
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

    def _bringup_device(self):
        """Perform the commands to fully setup the device."""
        if util.is_BSD():
            self.__bringup_device_on_bsd()
        else:
            self.__bringup_device_on_linux()

    def __bringup_static_routes_on_bsd(self, net_address, gateway):
        util.subp(
            ['route', '-4', 'add', '-net', net_address, gateway], capture=True)
        self.cleanup_cmds.insert(
            0, ['route', '-4', 'delete', '-net', net_address, gateway],
            capture=True)

    def __bringup_static_routes_on_linux(self, net_address, gateway):
        via_arg = ['via', gateway]
        util.subp(
            ['ip', '-4', 'route', 'add', net_address] + via_arg +
            ['dev', self.interface], capture=True)
        self.cleanup_cmds.insert(
            0, ['ip', '-4', 'route', 'del', net_address] + via_arg +
            ['dev', self.interface])

    def _bringup_static_routes(self):
        # static_routes = [("169.254.169.254/32", "130.56.248.255"),
        #                  ("0.0.0.0/0", "130.56.240.1")]
        for net_address, gateway in self.static_routes:
            if gateway != "0.0.0.0/0":
                if util.is_BSD():
                    self.__bringup_static_routes_on_bsd(net_address, gateway)
                else:
                    self.__bringup_static_routes_on_linux(net_address, gateway)

    def __bringup_router_on_bsd(self):
        """Perform the commands to fully setup the router if needed."""
        # Check if a default route exists and exit if it does
        out, _ = util.subp(['route', 'show', 'default'], capture=True)
        if 'default' in out:
            LOG.debug(
                'Skip ephemeral route setup. %s already has default route: %s',
                self.interface, out.strip())
            return
        util.subp(
            ['route', '-4', 'add', 'default', self.router], capture=True)
        self.cleanup_cmds.insert(
            0,
            ['route', '-4', 'delete', 'default', self.router])

    def __bringup_router_on_linux(self):
        """Perform the ip commands to fully setup the router if needed."""
        # Check if a default route exists and exit if it does
        out, _ = util.subp(['ip', 'route', 'show', '0.0.0.0/0'], capture=True)
        if 'default' in out:
            LOG.debug(
                'Skip ephemeral route setup. %s already has default route: %s',
                self.interface, out.strip())
            return
        util.subp(
            ['ip', '-4', 'route', 'add', self.router, 'dev', self.interface,
             'src', self.ip], capture=True)
        self.cleanup_cmds.insert(
            0,
            ['ip', '-4', 'route', 'del', self.router, 'dev', self.interface,
             'src', self.ip])
        util.subp(
            ['ip', '-4', 'route', 'add', 'default', 'via', self.router,
             'dev', self.interface], capture=True)
        self.cleanup_cmds.insert(
            0, ['ip', '-4', 'route', 'del', 'default', 'dev', self.interface])

    def _bringup_router(self):
        """Perform the commands to fully setup the router if needed."""
        if util.is_BSD():
            self.__bringup_router_on_bsd()
        else:
            self.__bringup_router_on_linux()


class RendererNotFoundError(RuntimeError):
    pass


# vi: ts=4 expandtab
