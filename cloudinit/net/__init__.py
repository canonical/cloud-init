# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Blake Rouse <blake.rouse@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import errno
import functools
import ipaddress
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from cloudinit import subp, util
from cloudinit.net.netops.iproute2 import Iproute2
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)
SYS_CLASS_NET = "/sys/class/net/"
DEFAULT_PRIMARY_INTERFACE = "eth0"
IPV6_DYNAMIC_TYPES = [
    "dhcp6",
    "ipv6_slaac",
    "ipv6_dhcpv6-stateless",
    "ipv6_dhcpv6-stateful",
]
OVS_INTERNAL_INTERFACE_LOOKUP_CMD = [
    "ovs-vsctl",
    "--format",
    "csv",
    "--no-headings",
    "--timeout",
    "10",
    "--columns",
    "name",
    "find",
    "interface",
    "type=internal",
]


def natural_sort_key(s, _nsre=re.compile("([0-9]+)")):
    """Sorting for Humans: natural sort order. Can be use as the key to sort
    functions.
    This will sort ['eth0', 'ens3', 'ens10', 'ens12', 'ens8', 'ens0'] as
    ['ens0', 'ens3', 'ens8', 'ens10', 'ens12', 'eth0'] instead of the simple
    python way which will produce ['ens0', 'ens10', 'ens12', 'ens3', 'ens8',
    'eth0']."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(_nsre, s)
    ]


def get_sys_class_path():
    """Simple function to return the global SYS_CLASS_NET."""
    return SYS_CLASS_NET


def sys_dev_path(devname, path=""):
    return get_sys_class_path() + devname + "/" + path


def read_sys_net(
    devname,
    path,
    translate=None,
    on_enoent=None,
    on_keyerror=None,
    on_einval=None,
):
    dev_path = sys_dev_path(devname, path)
    try:
        contents = util.load_text_file(dev_path)
    except (OSError, IOError) as e:
        e_errno = getattr(e, "errno", None)
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
            LOG.debug(
                "Found unexpected (not translatable) value '%s' in '%s",
                contents,
                dev_path,
            )
            raise


def read_sys_net_safe(iface, field, translate=None):
    def on_excp_false(e):
        return False

    return read_sys_net(
        iface,
        field,
        on_keyerror=on_excp_false,
        on_enoent=on_excp_false,
        on_einval=on_excp_false,
        translate=translate,
    )


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
    translate = {"up": True, "unknown": True, "down": False}
    return read_sys_net_safe(devname, "operstate", translate=translate)


def is_bridge(devname):
    return os.path.exists(sys_dev_path(devname, "bridge"))


def is_bond(devname):
    return os.path.exists(sys_dev_path(devname, "bonding"))


def get_master(devname):
    """Return the master path for devname, or None if no master"""
    path = sys_dev_path(devname, path="master")
    if os.path.exists(path):
        return path
    return None


def master_is_bridge_or_bond(devname):
    """Return a bool indicating if devname's master is a bridge or bond"""
    master_path = get_master(devname)
    if master_path is None:
        return False
    bonding_path = os.path.join(master_path, "bonding")
    bridge_path = os.path.join(master_path, "bridge")
    return os.path.exists(bonding_path) or os.path.exists(bridge_path)


def master_is_openvswitch(devname):
    """Return a bool indicating if devname's master is openvswitch"""
    master_path = get_master(devname)
    if master_path is None:
        return False
    ovs_path = sys_dev_path(devname, path="upper_ovs-system")
    return os.path.exists(ovs_path)


def is_ib_interface(devname):
    return read_sys_net_safe(devname, "type") == "32"


@functools.lru_cache(maxsize=None)
def openvswitch_is_installed() -> bool:
    """Return a bool indicating if Open vSwitch is installed in the system."""
    ret = bool(subp.which("ovs-vsctl"))
    if not ret:
        LOG.debug(
            "ovs-vsctl not in PATH; not detecting Open vSwitch interfaces"
        )
    return ret


@functools.lru_cache(maxsize=None)
def get_ovs_internal_interfaces() -> list:
    """Return a list of the names of OVS internal interfaces on the system.

    These will all be strings, and are used to exclude OVS-specific interface
    from cloud-init's network configuration handling.
    """
    try:
        out, _err = subp.subp(OVS_INTERNAL_INTERFACE_LOOKUP_CMD)
    except subp.ProcessExecutionError as exc:
        if "database connection failed" in exc.stderr:
            LOG.info(
                "Open vSwitch is not yet up; no interfaces will be detected as"
                " OVS-internal"
            )
            return []
        raise
    else:
        return out.splitlines()


def is_openvswitch_internal_interface(devname: str) -> bool:
    """Returns True if this is an OVS internal interface.

    If OVS is not installed or not yet running, this will return False.
    """
    if not openvswitch_is_installed():
        return False
    ovs_bridges = get_ovs_internal_interfaces()
    if devname in ovs_bridges:
        LOG.debug("Detected %s as an OVS interface", devname)
        return True
    return False


def is_netfailover(devname, driver=None):
    """netfailover driver uses 3 nics, master, primary and standby.
    this returns True if the device is either the primary or standby
    as these devices are to be ignored.
    """
    if driver is None:
        driver = device_driver(devname)
    if is_netfail_primary(devname, driver) or is_netfail_standby(
        devname, driver
    ):
        return True
    return False


def get_dev_features(devname):
    """Returns a str from reading /sys/class/net/<devname>/device/features."""
    features = ""
    try:
        features = read_sys_net(devname, "device/features")
    except Exception:
        pass
    return features


def has_netfail_standby_feature(devname):
    """Return True if VIRTIO_NET_F_STANDBY bit (62) is set.

    https://github.com/torvalds/linux/blob/ \
        089cf7f6ecb266b6a4164919a2e69bd2f938374a/ \
        include/uapi/linux/virtio_net.h#L60
    """
    features = get_dev_features(devname)
    if not features or len(features) < 64:
        return False
    return features[62] == "1"


def is_netfail_master(devname, driver=None) -> bool:
    """A device is a "netfail master" device if:

    - The device does NOT have the 'master' sysfs attribute
    - The device driver is 'virtio_net'
    - The device has the standby feature bit set

    Return True if all of the above is True.
    """
    if get_master(devname) is not None:
        return False

    if driver is None:
        driver = device_driver(devname)

    if driver != "virtio_net":
        return False

    if not has_netfail_standby_feature(devname):
        return False

    return True


def is_netfail_primary(devname, driver=None):
    """A device is a "netfail primary" device if:

    - the device has a 'master' sysfs file
    - the device driver is not 'virtio_net'
    - the 'master' sysfs file points to device with virtio_net driver
    - the 'master' device has the 'standby' feature bit set

    Return True if all of the above is True.
    """
    # /sys/class/net/<devname>/master -> ../../<master devname>
    master_sysfs_path = sys_dev_path(devname, path="master")
    if not os.path.exists(master_sysfs_path):
        return False

    if driver is None:
        driver = device_driver(devname)

    if driver == "virtio_net":
        return False

    master_devname = os.path.basename(os.path.realpath(master_sysfs_path))
    master_driver = device_driver(master_devname)
    if master_driver != "virtio_net":
        return False

    master_has_standby = has_netfail_standby_feature(master_devname)
    if not master_has_standby:
        return False

    return True


def is_netfail_standby(devname, driver=None):
    """A device is a "netfail standby" device if:

    - The device has a 'master' sysfs attribute
    - The device driver is 'virtio_net'
    - The device has the standby feature bit set

    Return True if all of the above is True.
    """
    if get_master(devname) is None:
        return False

    if driver is None:
        driver = device_driver(devname)

    if driver != "virtio_net":
        return False

    if not has_netfail_standby_feature(devname):
        return False

    return True


def is_renamed(devname):
    """
    /* interface name assignment types (sysfs name_assign_type attribute) */
    #define NET_NAME_UNKNOWN      0  /* unknown origin (not exposed to user) */
    #define NET_NAME_ENUM         1  /* enumerated by kernel */
    #define NET_NAME_PREDICTABLE  2  /* predictably named by the kernel */
    #define NET_NAME_USER         3  /* provided by user-space */
    #define NET_NAME_RENAMED      4  /* renamed by user-space */
    """
    name_assign_type = read_sys_net_safe(devname, "name_assign_type")
    if name_assign_type and name_assign_type in ["3", "4"]:
        return True
    return False


def is_vlan(devname):
    uevent = str(read_sys_net_safe(devname, "uevent"))
    return "DEVTYPE=vlan" in uevent.splitlines()


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
    if util.is_FreeBSD() or util.is_DragonFlyBSD():
        return list(get_interfaces_by_mac().values())

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
    return cfg.get("config") == "disabled"


def find_candidate_nics() -> List[str]:
    """Get the list of network interfaces viable for networking.

    @return List of interfaces, sorted naturally.
    """
    if util.is_FreeBSD() or util.is_DragonFlyBSD():
        return find_candidate_nics_on_freebsd()
    elif util.is_NetBSD() or util.is_OpenBSD():
        return find_candidate_nics_on_netbsd_or_openbsd()
    else:
        return find_candidate_nics_on_linux()


def find_fallback_nic() -> Optional[str]:
    """Get the name of the 'fallback' network device."""
    if util.is_FreeBSD() or util.is_DragonFlyBSD():
        return find_fallback_nic_on_freebsd()
    elif util.is_NetBSD() or util.is_OpenBSD():
        return find_fallback_nic_on_netbsd_or_openbsd()
    else:
        return find_fallback_nic_on_linux()


def find_candidate_nics_on_netbsd_or_openbsd() -> List[str]:
    """Get the names of the candidate network devices on NetBSD/OpenBSD.

    @return list of sorted interfaces
    """
    return sorted(get_interfaces_by_mac().values(), key=natural_sort_key)


def find_fallback_nic_on_netbsd_or_openbsd() -> Optional[str]:
    """Get the 'fallback' network device name on NetBSD/OpenBSD.

    @return default interface, or None
    """
    names = find_candidate_nics_on_netbsd_or_openbsd()
    if names:
        return names[0]

    return None


def find_candidate_nics_on_freebsd() -> List[str]:
    """Get the names of the candidate network devices on FreeBSD.

    @return List of sorted interfaces.
    """
    stdout, _stderr = subp.subp(["ifconfig", "-l", "-u", "ether"])
    values = stdout.split()
    if values:
        return values

    # On FreeBSD <= 10, 'ifconfig -l' ignores the interfaces with DOWN
    # status
    return sorted(get_interfaces_by_mac().values(), key=natural_sort_key)


def find_fallback_nic_on_freebsd() -> Optional[str]:
    """Get the 'fallback' network device name on FreeBSD.

    @return List of sorted interfaces.
    """
    names = find_candidate_nics_on_freebsd()
    if names:
        return names[0]

    return None


def find_candidate_nics_on_linux() -> List[str]:
    """Get the names of the candidate network devices on Linux.

    @return List of sorted interfaces.
    """
    if "net.ifnames=0" in util.get_cmdline():
        LOG.debug("Stable ifnames disabled by net.ifnames=0 in /proc/cmdline")
    else:
        unstable = [
            device
            for device in get_devicelist()
            if device != "lo" and not is_renamed(device)
        ]
        if len(unstable):
            LOG.debug(
                "Found unstable nic names: %s; calling udevadm settle",
                unstable,
            )
            msg = "Waiting for udev events to settle"
            util.log_time(LOG.debug, msg, func=util.udevadm_settle)

    # sort into interfaces with carrier, interfaces which could have carrier,
    # and ignore interfaces that are definitely disconnected
    connected = []
    possibly_connected = []
    for interface, _, _, _ in get_interfaces(
        filter_openvswitch_internal=False,
        filter_slave_if_master_not_bridge_bond_openvswitch=False,
        filter_vlan=False,
        filter_without_own_mac=False,
        filter_zero_mac=False,
        log_filtered_reasons=True,
    ):
        if interface == "lo":
            continue
        if interface.startswith("veth"):
            LOG.debug("Ignoring veth interface: %s", interface)
            continue
        carrier = read_sys_net_int(interface, "carrier")
        if carrier:
            connected.append(interface)
            continue
        LOG.debug("Interface has no carrier: %s", interface)
        # check if nic is dormant or down, as this may make a nick appear to
        # not have a carrier even though it could acquire one when brought
        # online by dhclient
        dormant = read_sys_net_int(interface, "dormant")
        if dormant:
            possibly_connected.append(interface)
            continue
        operstate = read_sys_net_safe(interface, "operstate")
        if operstate in ["dormant", "down", "lowerlayerdown", "unknown"]:
            possibly_connected.append(interface)
            continue

        LOG.debug("Interface ignored: %s", interface)

    # Order the NICs:
    # 1. DEFAULT_PRIMARY_INTERFACE, if connected.
    # 2. Remaining connected interfaces, naturally sorted.
    # 3. DEFAULT_PRIMARY_INTERFACE, if possibly connected.
    # 4. Remaining possibly connected interfaces, naturally sorted.
    sorted_interfaces = []
    for interfaces in [connected, possibly_connected]:
        interfaces = sorted(interfaces, key=natural_sort_key)
        if DEFAULT_PRIMARY_INTERFACE in interfaces:
            interfaces.remove(DEFAULT_PRIMARY_INTERFACE)
            interfaces.insert(0, DEFAULT_PRIMARY_INTERFACE)
        sorted_interfaces += interfaces

    return sorted_interfaces


def find_fallback_nic_on_linux() -> Optional[str]:
    """Get the 'fallback' network device name on Linux.

    @return List of sorted interfaces.
    """
    names = find_candidate_nics_on_linux()
    if names:
        return names[0]

    return None


def generate_fallback_config(config_driver=None):
    """Generate network cfg v2 for dhcp on the NIC most likely connected."""
    if not config_driver:
        config_driver = False

    target_name = find_fallback_nic()
    if not target_name:
        # can't read any interfaces addresses (or there are none); give up
        return None

    # netfail cannot use mac for matching, they have duplicate macs
    if is_netfail_master(target_name):
        match = {"name": target_name}
    else:
        match = {
            "macaddress": read_sys_net_safe(target_name, "address").lower()
        }
    cfg = {
        "dhcp4": True,
        "dhcp6": True,
        "set-name": target_name,
        "match": match,
    }
    if config_driver:
        driver = device_driver(target_name)
        if driver:
            cfg["match"]["driver"] = driver
    nconf = {"ethernets": {target_name: cfg}, "version": 2}
    return nconf


def extract_physdevs(netcfg):
    def _version_1(netcfg):
        physdevs = []
        for ent in netcfg.get("config", {}):
            if ent.get("type") != "physical":
                continue
            mac = ent.get("mac_address")
            if not mac:
                continue
            name = ent.get("name")
            driver = ent.get("params", {}).get("driver")
            device_id = ent.get("params", {}).get("device_id")
            if not driver:
                driver = device_driver(name)
            if not device_id:
                device_id = device_devid(name)
            physdevs.append([mac, name, driver, device_id])
        return physdevs

    def _version_2(netcfg):
        physdevs = []
        for ent in netcfg.get("ethernets", {}).values():
            # only rename if configured to do so
            name = ent.get("set-name")
            if not name:
                continue
            # cloud-init requires macaddress for renaming
            mac = ent.get("match", {}).get("macaddress")
            if not mac:
                continue
            driver = ent.get("match", {}).get("driver")
            device_id = ent.get("match", {}).get("device_id")
            if not driver:
                driver = device_driver(name)
            if not device_id:
                device_id = device_devid(name)
            physdevs.append([mac, name, driver, device_id])
        return physdevs

    version = netcfg.get("version")
    if version == 1:
        return _version_1(netcfg)
    elif version == 2:
        return _version_2(netcfg)

    raise RuntimeError("Unknown network config version: %s" % version)


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
            "downable": None,
            "device_id": device_id,
            "driver": driver,
            "mac": mac.lower(),
            "name": name,
            "up": is_up(name),
        }

    if check_downable:
        nmatch = re.compile(r"[0-9]+:\s+(\w+)[@:]")
        ipv6, _err = subp.subp(
            ["ip", "-6", "addr", "show", "permanent", "scope", "global"],
            capture=True,
        )
        ipv4, _err = subp.subp(["ip", "-4", "addr", "show"], capture=True)

        nics_with_addresses = set()
        for bytes_out in (ipv6, ipv4):
            nics_with_addresses.update(nmatch.findall(bytes_out))

        for d in cur_info.values():
            d["downable"] = (
                d["up"] is False or d["name"] not in nics_with_addresses
            )

    return cur_info


def _rename_interfaces(
    renames, strict_present=True, strict_busy=True, current_info=None
):

    if not len(renames):
        LOG.debug("no interfaces to rename")
        return

    if current_info is None:
        current_info = _get_current_rename_info()

    cur_info = {}
    for name, data in current_info.items():
        cur = data.copy()
        if cur.get("mac"):
            cur["mac"] = cur["mac"].lower()
        cur["name"] = name
        cur_info[name] = cur

    LOG.debug("Detected interfaces %s", cur_info)

    def update_byname(bymac):
        return dict((data["name"], data) for data in bymac.values())

    ops = []
    errors = []
    ups = []
    cur_byname = update_byname(cur_info)
    tmpname_fmt = "cirename%d"
    tmpi = -1

    def entry_match(data, mac, driver, device_id):
        """match if set and in data"""
        if mac and driver and device_id:
            return (
                data["mac"] == mac
                and data["driver"] == driver
                and data["device_id"] == device_id
            )
        elif mac and driver:
            return data["mac"] == mac and data["driver"] == driver
        elif mac:
            return data["mac"] == mac

        return False

    def find_entry(mac, driver, device_id):
        match = [
            data
            for data in cur_info.values()
            if entry_match(data, mac, driver, device_id)
        ]
        if len(match):
            if len(match) > 1:
                msg = (
                    'Failed to match a single device. Matched devices "%s"'
                    ' with search values "(mac:%s driver:%s device_id:%s)"'
                    % (match, mac, driver, device_id)
                )
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
                    ", not available." % (mac, new_name)
                )
            continue

        cur_name = cur.get("name")
        if cur_name == new_name:
            # nothing to do
            continue

        if not cur_name:
            if strict_present:
                errors.append(
                    "[nic not present] Cannot rename mac=%s to %s"
                    ", not available." % (mac, new_name)
                )
            continue

        if cur["up"]:
            msg = "[busy] Error renaming mac=%s from %s to %s"
            if not cur["downable"]:
                if strict_busy:
                    errors.append(msg % (mac, cur_name, new_name))
                continue
            cur["up"] = False
            cur_ops.append(("down", mac, new_name, (cur_name,)))
            ups.append(("up", mac, new_name, (new_name,)))

        if new_name in cur_byname:
            target = cur_byname[new_name]
            if target["up"]:
                msg = "[busy-target] Error renaming mac=%s from %s to %s."
                if not target["downable"]:
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
            target["name"] = tmp_name
            cur_byname = update_byname(cur_info)
            if target["up"]:
                ups.append(("up", mac, new_name, (tmp_name,)))

        cur_ops.append(("rename", mac, new_name, (cur["name"], new_name)))
        cur["name"] = new_name
        cur_byname = update_byname(cur_info)
        ops += cur_ops

    opmap = {
        "rename": Iproute2.link_rename,
        "down": Iproute2.link_down,
        "up": Iproute2.link_up,
    }

    if len(ops) + len(ups) == 0:
        if len(errors):
            LOG.warning(
                "Unable to rename interfaces: %s due to errors: %s",
                renames,
                errors,
            )
        else:
            LOG.debug("no work necessary for renaming of %s", renames)
    else:
        LOG.debug("Renamed %s with ops %s", renames, ops + ups)

        for op, mac, new_name, params in ops + ups:
            try:
                opmap.get(op)(*params)
            except Exception as e:
                errors.append(
                    "[unknown] Error performing %s%s for %s, %s: %s"
                    % (op, params, mac, new_name, e)
                )

    if len(errors):
        raise RuntimeError("\n".join(errors))


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
    if read_sys_net_safe(ifname, "type") == "32":
        mac = get_interface_mac(ifname)
        if mac and ethernet_format:
            # Use bytes 13-15 and 18-20 of the hardware address.
            mac = mac[36:-14] + mac[51:]
        return mac


def get_interfaces_by_mac() -> dict:
    if util.is_FreeBSD() or util.is_DragonFlyBSD():
        return get_interfaces_by_mac_on_freebsd()
    elif util.is_NetBSD():
        return get_interfaces_by_mac_on_netbsd()
    elif util.is_OpenBSD():
        return get_interfaces_by_mac_on_openbsd()
    else:
        return get_interfaces_by_mac_on_linux()


def find_interface_name_from_mac(mac: str) -> Optional[str]:
    for interface_mac, interface_name in get_interfaces_by_mac().items():
        if mac.lower() == interface_mac.lower():
            return interface_name
    return None


def get_interfaces_by_mac_on_freebsd() -> dict:
    (out, _) = subp.subp(["ifconfig", "-a", "ether"])

    # flatten each interface block in a single line
    def flatten(out):
        curr_block = ""
        for line in out.split("\n"):
            if line.startswith("\t"):
                curr_block += line
            else:
                if curr_block:
                    yield curr_block
                curr_block = line
        yield curr_block

    # looks for interface and mac in a list of flatten block
    def find_mac(flat_list):
        for block in flat_list:
            m = re.search(
                r"^(?P<ifname>\S*): .*ether\s(?P<mac>[\da-f:]{17}).*", block
            )
            if m:
                yield (m.group("mac"), m.group("ifname"))

    results = {mac: ifname for mac, ifname in find_mac(flatten(out))}
    return results


def get_interfaces_by_mac_on_netbsd() -> dict:
    ret = {}
    re_field_match = (
        r"(?P<ifname>\w+).*address:\s"
        r"(?P<mac>([\da-f]{2}[:-]){5}([\da-f]{2})).*"
    )
    (out, _) = subp.subp(["ifconfig", "-a"])
    if_lines = re.sub(r"\n\s+", " ", out).splitlines()
    for line in if_lines:
        m = re.match(re_field_match, line)
        if m:
            fields = m.groupdict()
            ret[fields["mac"]] = fields["ifname"]
    return ret


def get_interfaces_by_mac_on_openbsd() -> dict:
    ret = {}
    re_field_match = (
        r"(?P<ifname>\w+).*lladdr\s"
        r"(?P<mac>([\da-f]{2}[:-]){5}([\da-f]{2})).*"
    )
    (out, _) = subp.subp(["ifconfig", "-a"])
    if_lines = re.sub(r"\n\s+", " ", out).splitlines()
    for line in if_lines:
        m = re.match(re_field_match, line)
        if m:
            fields = m.groupdict()
            ret[fields["mac"]] = fields["ifname"]
    return ret


def get_interfaces_by_mac_on_linux() -> dict:
    """Build a dictionary of tuples {mac: name}.

    Bridges and any devices that have a 'stolen' mac are excluded."""
    ret: dict = {}

    for name, mac, driver, _devid in get_interfaces():
        if mac in ret:
            # This is intended to be a short-term fix of LP: #1997922
            # Long term, we should better handle configuration of virtual
            # devices where duplicate MACs are expected early in boot if
            # cloud-init happens to enumerate network interfaces before drivers
            # have fully initialized the leader/subordinate relationships for
            # those devices or switches.
            if driver in ("fsl_enetc", "mscc_felix", "qmi_wwan"):
                LOG.debug(
                    "Ignoring duplicate macs from '%s' and '%s' due to "
                    "driver '%s'.",
                    name,
                    ret[mac],
                    driver,
                )
                continue

            msg = "duplicate mac found! both '%s' and '%s' have mac '%s'." % (
                name,
                ret[mac],
                mac,
            )
            raise RuntimeError(msg)

        ret[mac] = name

        # Pretend that an Infiniband GUID is an ethernet address for Openstack
        # configuration purposes
        # TODO: move this format to openstack
        ib_mac = get_ib_interface_hwaddr(name, True)
        if ib_mac:

            # If an Ethernet mac address happens to collide with a few bits in
            # an IB GUID, prefer the ethernet address.
            #
            # Log a message in case a user is troubleshooting openstack, but
            # don't fall over, since this really isn't _a_ problem, and
            # openstack makes weird assumptions that cause it to fail it's
            # really not _our_ problem.
            #
            # These few bits selected in get_ib_interface_hwaddr() are not
            # guaranteed to be globally unique in InfiniBand, and really make
            # no sense to compare them to Ethernet mac addresses. This appears
            # to be a # workaround for openstack-specific behavior[1], and for
            # now leave it to avoid breaking openstack
            # but this should be removed from get_interfaces_by_mac_on_linux()
            # because IB GUIDs are not mac addresses, and operate on a separate
            # L2 protocol so address collision doesn't matter.
            #
            # [1] sources/helpers/openstack.py:convert_net_json() expects
            # net.get_interfaces_by_mac() to return IB addresses in this format
            if ib_mac not in ret:
                ret[ib_mac] = name
            else:
                LOG.warning(
                    "Ethernet and InfiniBand interfaces have the same address"
                    " both '%s' and '%s' have address '%s'.",
                    name,
                    ret[ib_mac],
                    ib_mac,
                )
    return ret


def get_interfaces(
    filter_hyperv_vf_with_synthetic: bool = True,
    filter_openvswitch_internal: bool = True,
    filter_slave_if_master_not_bridge_bond_openvswitch: bool = True,
    filter_vlan: bool = True,
    filter_without_own_mac: bool = True,
    filter_zero_mac: bool = True,
    log_filtered_reasons: bool = False,
) -> list:
    """Return list of interface tuples (name, mac, driver, device_id)

    Bridges and any devices that have a 'stolen' mac are excluded."""
    filtered_logger = LOG.debug if log_filtered_reasons else lambda *args: None
    ret = []
    devs = get_devicelist()
    # 16 somewhat arbitrarily chosen.  Normally a mac is 6 '00:' tokens.
    zero_mac = ":".join(("00",) * 16)
    for name in devs:
        if filter_without_own_mac and not interface_has_own_mac(name):
            continue
        if is_bridge(name):
            filtered_logger("Ignoring bridge interface: %s", name)
            continue
        if filter_vlan and is_vlan(name):
            continue
        if is_bond(name):
            filtered_logger("Ignoring bond interface: %s", name)
            continue
        if (
            filter_slave_if_master_not_bridge_bond_openvswitch
            and get_master(name) is not None
            and not master_is_bridge_or_bond(name)
            and not master_is_openvswitch(name)
        ):
            continue
        if is_netfailover(name):
            filtered_logger("Ignoring failover interface: %s", name)
            continue
        mac = get_interface_mac(name)
        # some devices may not have a mac (tun0)
        if not mac:
            filtered_logger("Ignoring interface without mac: %s", name)
            continue
        # skip nics that have no mac (00:00....)
        if filter_zero_mac and name != "lo" and mac == zero_mac[: len(mac)]:
            continue
        if filter_openvswitch_internal and is_openvswitch_internal_interface(
            name
        ):
            continue
        driver = device_driver(name)
        ret.append((name, mac, driver, device_devid(name)))

    # Last-pass filter(s) which need the full device list to perform properly.
    if filter_hyperv_vf_with_synthetic:
        filter_hyperv_vf_with_synthetic_interface(filtered_logger, ret)

    return ret


def filter_hyperv_vf_with_synthetic_interface(
    filtered_logger: Callable[..., None],
    interfaces: List[Tuple[str, str, str, str]],
) -> None:
    """Filter Hyper-V SR-IOV/VFs when used with synthetic hv_netvsc.

    Hyper-V's netvsc driver may register an SR-IOV/VF interface with a mac
    that matches the synthetic (hv_netvsc) interface.  This VF will be
    enslaved to the synthetic interface, but cloud-init may be racing this
    process.  The [perhaps-yet-to-be-enslaved] VF should never be directly
    configured, so we filter interfaces that duplicate any hv_netvsc mac
    address, as this the most reliable indicator that it is meant to be
    subordinate to the synthetic interface.

    VF drivers will be mlx4_core, mlx5_core, or mana.  However, given that
    this list of drivers has changed over time and mana's dependency on
    hv_netvsc is expected to be removed in the future, we no longer rely
    on these names. Note that this will not affect mlx4/5 instances outside
    of Hyper-V, as it only affects environments where hv_netvsc is present.
    """
    hv_netvsc_mac_to_name = {
        i[1]: i[0] for i in interfaces if i[2] == "hv_netvsc"
    }
    interfaces_to_remove = [
        i
        for i in interfaces
        if i[1] in hv_netvsc_mac_to_name and i[2] != "hv_netvsc"
    ]

    for interface in interfaces_to_remove:
        name, mac, driver, _ = interface
        filtered_logger(
            "Ignoring %r VF interface with driver %r due to "
            "synthetic hv_netvsc interface %r with mac address %r.",
            name,
            driver,
            hv_netvsc_mac_to_name[mac],
            mac,
        )
        interfaces.remove(interface)


def get_ib_hwaddrs_by_interface():
    """Build a dictionary mapping Infiniband interface names to their hardware
    address."""
    ret = {}
    for name, _, _, _ in get_interfaces():
        ib_mac = get_ib_interface_hwaddr(name, False)
        if ib_mac:
            if ib_mac in ret:
                raise RuntimeError(
                    "duplicate mac found! both '%s' and '%s' have mac '%s'"
                    % (name, ret[ib_mac], ib_mac)
                )
            ret[name] = ib_mac
    return ret


def has_url_connectivity(url_data: Dict[str, Any]) -> bool:
    """Return true when the instance has access to the provided URL.

    Logs a warning if url is not the expected format.

    url_data is a dictionary of kwargs to send to readurl. E.g.:

    has_url_connectivity({
        "url": "http://example.invalid",
        "headers": {"some": "header"},
        "timeout": 10
    })
    """
    if "url" not in url_data:
        LOG.warning(
            "Ignoring connectivity check. No 'url' to check in %s", url_data
        )
        return False
    url = url_data["url"]
    try:
        result = urlparse(url)
        if not any([result.scheme == "http", result.scheme == "https"]):
            LOG.warning(
                "Ignoring connectivity check. Invalid URL scheme %s",
                url.scheme,
            )
            return False
    except ValueError as err:
        LOG.warning("Ignoring connectivity check. Invalid URL %s", err)
        return False
    if "timeout" not in url_data:
        url_data["timeout"] = 5
    try:
        readurl(**url_data)
    except UrlError:
        return False
    return True


def maybe_get_address(convert_to_address: Callable, address: str, **kwargs):
    """Use a function to return an address. If conversion throws a ValueError
    exception return False.

    :param check_cb:
        Test function, must return a truthy value
    :param address:
        The string to test.

    :return:
        Address or False

    """
    try:
        return convert_to_address(address, **kwargs)
    except ValueError:
        return False


def is_ip_address(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IP address.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IP address or not.
    """
    return bool(maybe_get_address(ipaddress.ip_address, address))


def is_ipv4_address(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv4 address.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IPv4 address or not.
    """
    return bool(maybe_get_address(ipaddress.IPv4Address, address))


def is_ipv6_address(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv6 address.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IPv4 address or not.
    """
    return bool(maybe_get_address(ipaddress.IPv6Address, address))


def is_ip_network(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv4 or IPv6 network.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IPv4 address or not.
    """
    return bool(maybe_get_address(ipaddress.ip_network, address, strict=False))


def is_ipv4_network(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv4 network.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IPv4 address or not.
    """
    return bool(
        maybe_get_address(ipaddress.IPv4Network, address, strict=False)
    )


def is_ipv6_network(address: str) -> bool:
    """Returns a bool indicating if ``s`` is an IPv6 network.

    :param address:
        The string to test.

    :return:
        A bool indicating if the string is an IPv4 address or not.
    """
    return bool(
        maybe_get_address(ipaddress.IPv6Network, address, strict=False)
    )


def is_ip_in_subnet(address: str, subnet: str) -> bool:
    """Returns a bool indicating if ``s`` is in subnet.

    :param address:
        The string of IP address.

    :param subnet:
        The string of subnet.

    :return:
        A bool indicating if the string is in subnet.
    """
    ip_address = ipaddress.ip_address(address)
    subnet_network = ipaddress.ip_network(subnet, strict=False)
    return ip_address in subnet_network


def should_add_gateway_onlink_flag(gateway: str, subnet: str) -> bool:
    """Returns a bool indicating if should add gateway onlink flag.

    :param gateway:
        The string of gateway address.

    :param subnet:
        The string of subnet.

    :return:
        A bool indicating if the string is in subnet.
    """
    try:
        return not is_ip_in_subnet(gateway, subnet)
    except ValueError as e:
        LOG.warning(
            "Failed to check whether gateway %s"
            " is contained within subnet %s: %s",
            gateway,
            subnet,
            e,
        )
        return False


def subnet_is_ipv6(subnet) -> bool:
    """Common helper for checking network_state subnets for ipv6."""
    # 'static6', 'dhcp6', 'ipv6_dhcpv6-stateful', 'ipv6_dhcpv6-stateless' or
    # 'ipv6_slaac'
    # This function is inappropriate for v2-based routes as routes defined
    # under v2 subnets can contain ipv4 and ipv6 simultaneously
    if subnet["type"].endswith("6") or subnet["type"] in IPV6_DYNAMIC_TYPES:
        # This is a request either static6 type or DHCPv6.
        return True
    elif subnet["type"] == "static" and is_ipv6_address(subnet.get("address")):
        return True
    return False


def net_prefix_to_ipv4_mask(prefix) -> str:
    """Convert a network prefix to an ipv4 netmask.

    This is the inverse of ipv4_mask_to_net_prefix.
        24 -> "255.255.255.0"
    Also supports input as a string."""
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def ipv4_mask_to_net_prefix(mask) -> int:
    """Convert an ipv4 netmask into a network prefix length.

    If the input is already an integer or a string representation of
    an integer, then int(mask) will be returned.
       "255.255.255.0" => 24
       str(24)         => 24
       "24"            => 24
    """
    return ipaddress.ip_network(f"0.0.0.0/{mask}").prefixlen


def ipv6_mask_to_net_prefix(mask) -> int:
    """Convert an ipv6 netmask (very uncommon) or prefix (64) to prefix.

    If the input is already an integer or a string representation of
    an integer, then int(mask) will be returned.
       "ffff:ffff:ffff::"  => 48
       "48"                => 48
    """
    try:
        # In the case the mask is already a prefix
        prefixlen = ipaddress.ip_network(f"::/{mask}").prefixlen
        return prefixlen
    except ValueError:
        # ValueError means mask is an IPv6 address representation and need
        # conversion.
        pass

    netmask = ipaddress.ip_address(mask)
    mask_int = int(netmask)
    # If the mask is all zeroes, just return it
    if mask_int == 0:
        return mask_int

    trailing_zeroes = min(
        ipaddress.IPV6LENGTH, (~mask_int & (mask_int - 1)).bit_length()
    )
    leading_ones = mask_int >> trailing_zeroes
    prefixlen = ipaddress.IPV6LENGTH - trailing_zeroes
    all_ones = (1 << prefixlen) - 1
    if leading_ones != all_ones:
        raise ValueError("Invalid network mask '%s'" % mask)

    return prefixlen


def mask_and_ipv4_to_bcast_addr(mask: str, ip: str) -> str:
    """Get string representation of broadcast address from an ip/mask pair"""
    return str(
        ipaddress.IPv4Network(f"{ip}/{mask}", strict=False).broadcast_address
    )


class RendererNotFoundError(RuntimeError):
    pass
