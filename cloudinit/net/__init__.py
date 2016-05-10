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
import os


from cloudinit import log as logging
from cloudinit.net import network_state
from cloudinit import util


LOG = logging.getLogger(__name__)
SYS_CLASS_NET = "/sys/class/net/"
LINKS_FNAME_PREFIX = "etc/systemd/network/50-cloud-init-"
DEFAULT_PRIMARY_INTERFACE = 'eth0'


def sys_dev_path(devname, path=""):
    return SYS_CLASS_NET + devname + "/" + path


def read_sys_net(devname, path, translate=None, enoent=None, keyerror=None):
    try:
        contents = ""
        with open(sys_dev_path(devname, path), "r") as fp:
            contents = fp.read().strip()
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
    except OSError as e:
        if e.errno == errno.ENOENT and enoent is not None:
            return enoent
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


def parse_net_config_data(net_config, skip_broken=True):
    """Parses the config, returns NetworkState object

    :param net_config: curtin network config dict
    """
    state = None
    if 'version' in net_config and 'config' in net_config:
        ns = network_state.NetworkState(version=net_config.get('version'),
                                        config=net_config.get('config'))
        ns.parse_config(skip_broken=skip_broken)
        state = ns.network_state
    return state


def parse_net_config(path, skip_broken=True):
    """Parses a curtin network configuration file and
       return network state"""
    ns = None
    net_config = util.read_conf(path)
    if 'network' in net_config:
        ns = parse_net_config_data(net_config.get('network'),
                                   skip_broken=skip_broken)
    return ns


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


# vi: ts=4 expandtab syntax=python
