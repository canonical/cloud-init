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
import glob
import os
import re

from curtin.log import LOG
from curtin.udev import generate_udev_rule
import curtin.util as util
import curtin.config as config
from . import network_state

SYS_CLASS_NET = "/sys/class/net/"

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


def parse_deb_config_data(ifaces, contents, src_dir, src_path):
    """Parses the file contents, placing result into ifaces.

    '_source_path' is added to every dictionary entry to define which file
    the configration information came from.

    :param ifaces: interface dictionary
    :param contents: contents of interfaces file
    :param src_dir: directory interfaces file was located
    :param src_path: file path the `contents` was read
    """
    currif = None
    for line in contents.splitlines():
        line = line.strip()
        if line.startswith('#'):
            continue
        split = line.split(' ')
        option = split[0]
        if option == "source-directory":
            parsed_src_dir = split[1]
            if not parsed_src_dir.startswith("/"):
                parsed_src_dir = os.path.join(src_dir, parsed_src_dir)
            for expanded_path in glob.glob(parsed_src_dir):
                dir_contents = os.listdir(expanded_path)
                dir_contents = [
                    os.path.join(expanded_path, path)
                    for path in dir_contents
                    if (os.path.isfile(os.path.join(expanded_path, path)) and
                        re.match("^[a-zA-Z0-9_-]+$", path) is not None)
                ]
                for entry in dir_contents:
                    with open(entry, "r") as fp:
                        src_data = fp.read().strip()
                    abs_entry = os.path.abspath(entry)
                    parse_deb_config_data(
                        ifaces, src_data,
                        os.path.dirname(abs_entry), abs_entry)
        elif option == "source":
            new_src_path = split[1]
            if not new_src_path.startswith("/"):
                new_src_path = os.path.join(src_dir, new_src_path)
            for expanded_path in glob.glob(new_src_path):
                with open(expanded_path, "r") as fp:
                    src_data = fp.read().strip()
                abs_path = os.path.abspath(expanded_path)
                parse_deb_config_data(
                    ifaces, src_data,
                    os.path.dirname(abs_path), abs_path)
        elif option == "auto":
            for iface in split[1:]:
                if iface not in ifaces:
                    ifaces[iface] = {
                        # Include the source path this interface was found in.
                        "_source_path": src_path
                    }
                ifaces[iface]['auto'] = True
        elif option == "iface":
            iface, family, method = split[1:4]
            if iface not in ifaces:
                ifaces[iface] = {
                    # Include the source path this interface was found in.
                    "_source_path": src_path
                }
            elif 'family' in ifaces[iface]:
                raise ParserError(
                    "Interface %s can only be defined once. "
                    "Re-defined in '%s'." % (iface, src_path))
            ifaces[iface]['family'] = family
            ifaces[iface]['method'] = method
            currif = iface
        elif option == "hwaddress":
            ifaces[currif]['hwaddress'] = split[1]
        elif option in NET_CONFIG_OPTIONS:
            ifaces[currif][option] = split[1]
        elif option in NET_CONFIG_COMMANDS:
            if option not in ifaces[currif]:
                ifaces[currif][option] = []
            ifaces[currif][option].append(' '.join(split[1:]))
        elif option.startswith('dns-'):
            if 'dns' not in ifaces[currif]:
                ifaces[currif]['dns'] = {}
            if option == 'dns-search':
                ifaces[currif]['dns']['search'] = []
                for domain in split[1:]:
                    ifaces[currif]['dns']['search'].append(domain)
            elif option == 'dns-nameservers':
                ifaces[currif]['dns']['nameservers'] = []
                for server in split[1:]:
                    ifaces[currif]['dns']['nameservers'].append(server)
        elif option.startswith('bridge_'):
            if 'bridge' not in ifaces[currif]:
                ifaces[currif]['bridge'] = {}
            if option in NET_CONFIG_BRIDGE_OPTIONS:
                bridge_option = option.replace('bridge_', '', 1)
                ifaces[currif]['bridge'][bridge_option] = split[1]
            elif option == "bridge_ports":
                ifaces[currif]['bridge']['ports'] = []
                for iface in split[1:]:
                    ifaces[currif]['bridge']['ports'].append(iface)
            elif option == "bridge_hw" and split[1].lower() == "mac":
                ifaces[currif]['bridge']['mac'] = split[2]
            elif option == "bridge_pathcost":
                if 'pathcost' not in ifaces[currif]['bridge']:
                    ifaces[currif]['bridge']['pathcost'] = {}
                ifaces[currif]['bridge']['pathcost'][split[1]] = split[2]
            elif option == "bridge_portprio":
                if 'portprio' not in ifaces[currif]['bridge']:
                    ifaces[currif]['bridge']['portprio'] = {}
                ifaces[currif]['bridge']['portprio'][split[1]] = split[2]
        elif option.startswith('bond-'):
            if 'bond' not in ifaces[currif]:
                ifaces[currif]['bond'] = {}
            bond_option = option.replace('bond-', '', 1)
            ifaces[currif]['bond'][bond_option] = split[1]
    for iface in ifaces.keys():
        if 'auto' not in ifaces[iface]:
            ifaces[iface]['auto'] = False


def parse_deb_config(path):
    """Parses a debian network configuration file."""
    ifaces = {}
    with open(path, "r") as fp:
        contents = fp.read().strip()
    abs_path = os.path.abspath(path)
    parse_deb_config_data(
        ifaces, contents,
        os.path.dirname(abs_path), abs_path)
    return ifaces


def parse_net_config_data(net_config):
    """Parses the config, returns NetworkState dictionary

    :param net_config: curtin network config dict
    """
    state = None
    if 'version' in net_config and 'config' in net_config:
        ns = network_state.NetworkState(version=net_config.get('version'),
                                        config=net_config.get('config'))
        ns.parse_config()
        state = ns.network_state

    return state


def parse_net_config(path):
    """Parses a curtin network configuration file and
       return network state"""
    ns = None
    net_config = config.load_config(path)
    if 'network' in net_config:
        ns = parse_net_config_data(net_config.get('network'))

    return ns


def render_persistent_net(network_state):
    ''' Given state, emit udev rules to map
        mac to ifname
    '''
    content = ""
    interfaces = network_state.get('interfaces')
    for iface in interfaces.values():
        # for physical interfaces write out a persist net udev rule
        if iface['type'] == 'physical' and \
           'name' in iface and 'mac_address' in iface:
            content += generate_udev_rule(iface['name'],
                                          iface['mac_address'])

    return content


# TODO: switch valid_map based on mode inet/inet6
def iface_add_subnet(iface, subnet):
    content = ""
    valid_map = [
        'address',
        'netmask',
        'broadcast',
        'metric',
        'gateway',
        'pointopoint',
        'mtu',
        'scope',
        'dns_search',
        'dns_nameservers',
    ]
    for key, value in subnet.items():
        if value and key in valid_map:
            if type(value) == list:
                value = " ".join(value)
            if '_' in key:
                key = key.replace('_', '-')
            content += "    {} {}\n".format(key, value)

    return content


# TODO: switch to valid_map for attrs
def iface_add_attrs(iface):
    content = ""
    ignore_map = [
        'type',
        'name',
        'inet',
        'mode',
        'index',
        'subnets',
    ]
    if iface['type'] not in ['bond', 'bridge']:
        ignore_map.append('mac_address')

    for key, value in iface.items():
        if value and key not in ignore_map:
            if type(value) == list:
                value = " ".join(value)
            content += "    {} {}\n".format(key, value)

    return content


def render_route(route):
    content = "up route add"
    mapping = {
        'network': '-net',
        'netmask': 'netmask',
        'gateway': 'gw',
        'metric': 'metric',
    }
    for k in ['network', 'netmask', 'gateway', 'metric']:
        if k in route:
            content += " %s %s" % (mapping[k], route[k])

    content += '\n'
    return content


def render_interfaces(network_state):
    ''' Given state, emit etc/network/interfaces content '''

    content = ""
    interfaces = network_state.get('interfaces')
    ''' Apply a sort order to ensure that we write out
        the physical interfaces first; this is critical for
        bonding
    '''
    order = {
        'physical': 0,
        'bond': 1,
        'bridge': 2,
        'vlan': 3,
    }
    content += "auto lo\niface lo inet loopback\n"
    for dnskey, value in network_state.get('dns', {}).items():
        if len(value):
            content += "    dns-{} {}\n".format(dnskey, " ".join(value))

    for iface in sorted(interfaces.values(),
                        key=lambda k: (order[k['type']], k['name'])):
        content += "auto {name}\n".format(**iface)

        subnets = iface.get('subnets', {})
        if subnets:
            for index, subnet in zip(range(0, len(subnets)), subnets):
                iface['index'] = index
                iface['mode'] = subnet['type']
                if iface['mode'].endswith('6'):
                    iface['inet'] += '6'
                elif iface['mode'] == 'static' and ":" in subnet['address']:
                    iface['inet'] += '6'
                if iface['mode'].startswith('dhcp'):
                    iface['mode'] = 'dhcp'

                if index == 0:
                    content += "iface {name} {inet} {mode}\n".format(**iface)
                else:
                    content += "auto {name}:{index}\n".format(**iface)
                    content += \
                        "iface {name}:{index} {inet} {mode}\n".format(**iface)

                content += iface_add_subnet(iface, subnet)
                content += iface_add_attrs(iface)
                content += "\n"
        else:
            content += "iface {name} {inet} {mode}\n".format(**iface)
            content += iface_add_attrs(iface)
            content += "\n"

    for route in network_state.get('routes'):
        content += render_route(route)

    # global replacements until v2 format
    content = content.replace('mac_address', 'hwaddress')
    return content


def render_network_state(target, network_state):
    eni = 'etc/network/interfaces'
    netrules = 'etc/udev/rules.d/70-persistent-net.rules'

    eni = os.path.sep.join((target, eni,))
    util.ensure_dir(os.path.dirname(eni))
    with open(eni, 'w+') as f:
        f.write(render_interfaces(network_state))

    netrules = os.path.sep.join((target, netrules,))
    util.ensure_dir(os.path.dirname(netrules))
    with open(netrules, 'w+') as f:
        f.write(render_persistent_net(network_state))

# vi: ts=4 expandtab syntax=python
