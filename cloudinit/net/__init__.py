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

import six
import yaml

LOG = logging.getLogger(__name__)
SYS_CLASS_NET = "/sys/class/net/"
LINKS_FNAME_PREFIX = "etc/systemd/network/50-cloud-init-"

NET_CONFIG_OPTIONS = [
    "address", "netmask", "broadcast", "network", "metric", "gateway",
    "pointtopoint", "media", "mtu", "hostname", "leasehours", "leasetime",
    "vendor", "client", "bootfile", "server", "hwaddr", "provider", "frame",
    "netnum", "endpoint", "local", "ttl",
]

NET_CONFIG_COMMANDS = [
    "pre-up", "up", "post-up", "down", "pre-down", "post-down",
]

NET_CONFIG_BRIDGE_OPTIONS = [
    "bridge_ageing", "bridge_bridgeprio", "bridge_fd", "bridge_gcinit",
    "bridge_hello", "bridge_maxage", "bridge_maxwait", "bridge_stp",
]
DEFAULT_PRIMARY_INTERFACE = 'eth0'

# NOTE(harlowja): some of these are similar to what is in cloudinit main
# source or utils tree/module but the reason that is done is so that this
# whole module can be easily extracted and placed into other
# code-bases (curtin for example).

def write_file(path, content):
    """Simple writing a file helper."""
    base_path = os.path.dirname(path)
    if not os.path.isdir(base_path):
        os.makedirs(base_path)
    with open(path, "wb+") as fh:
        if isinstance(content, six.text_type):
            content = content.encode("utf8")
        fh.write(content)


def read_file(path, decode='utf8', enoent=None):
    try:
        with open(path, "rb") as fh:
            contents = fh.load()
    except OSError as e:
        if e.errno == errno.ENOENT and enoent is not None:
            return enoent
        raise
    if decode:
        return contents.decode(decode)
    return contents


def dump_yaml(obj):
    return yaml.safe_dump(obj,
                          line_break="\n",
                          indent=4,
                          explicit_start=True,
                          explicit_end=True,
                          default_flow_style=False)


def read_yaml_file(path):
    val = yaml.safe_load(read_file(path))
    if not isinstance(val, dict):
        gotten_type_name = type(val).__name__
        raise TypeError("Expected dict to be loaded from %s, got"
                        " '%s' instead" % (path, gotten_type_name))
    return val


def sys_dev_path(devname, path=""):
    return SYS_CLASS_NET + devname + "/" + path


def read_sys_net(devname, path, translate=None, enoent=None, keyerror=None):
    contents = read_file(sys_dev_path(devname, path), enoent=enoent)
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
    """Raised when parser has issue parsing the interfaces file."""


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
    data = read_file(fname)
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


# vi: ts=4 expandtab syntax=python
