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

import base64
import errno
import glob
import gzip
import io
import os
import re
import shlex

from cloudinit import log as logging
from cloudinit import util
from .udev import generate_udev_rule
from . import network_state

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
    """Parses the config, returns NetworkState object

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
    net_config = util.read_conf(path)
    if 'network' in net_config:
        ns = parse_net_config_data(net_config.get('network'))

    return ns


def _load_shell_content(content, add_empty=False, empty_val=None):
    """Given shell like syntax (key=value\nkey2=value2\n) in content
       return the data in dictionary form.  If 'add_empty' is True
       then add entries in to the returned dictionary for 'VAR='
       variables.  Set their value to empty_val."""
    data = {}
    for line in shlex.split(content):
        key, value = line.split("=", 1)
        if not value:
            value = empty_val
        if add_empty or value:
            data[key] = value

    return data


def _klibc_to_config_entry(content, mac_addrs=None):
    """Convert a klibc writtent shell content file to a 'config' entry
    When ip= is seen on the kernel command line in debian initramfs
    and networking is brought up, ipconfig will populate
    /run/net-<name>.cfg.

    The files are shell style syntax, and examples are in the tests
    provided here.  There is no good documentation on this unfortunately.

    DEVICE=<name> is expected/required and PROTO should indicate if
    this is 'static' or 'dhcp'.
    """

    if mac_addrs is None:
        mac_addrs = {}

    data = _load_shell_content(content)
    try:
        name = data['DEVICE']
    except KeyError:
        raise ValueError("no 'DEVICE' entry in data")

    # ipconfig on precise does not write PROTO
    proto = data.get('PROTO')
    if not proto:
        if data.get('filename'):
            proto = 'dhcp'
        else:
            proto = 'static'

    if proto not in ('static', 'dhcp'):
        raise ValueError("Unexpected value for PROTO: %s" % proto)

    iface = {
        'type': 'physical',
        'name': name,
        'subnets': [],
    }

    if name in mac_addrs:
        iface['mac_address'] = mac_addrs[name]

    # originally believed there might be IPV6* values
    for v, pre in (('ipv4', 'IPV4'),):
        # if no IPV4ADDR or IPV6ADDR, then go on.
        if pre + "ADDR" not in data:
            continue
        subnet = {'type': proto, 'control': 'manual'}

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
        files = glob.glob('/run/net*.conf')

    entries = []
    names = {}
    for cfg_file in files:
        name, entry = _klibc_to_config_entry(util.load_file(cfg_file),
                                             mac_addrs=mac_addrs)
        if name in names:
            raise ValueError(
                "device '%s' defined multiple times: %s and %s" % (
                    name, names[name], cfg_file))

        names[name] = cfg_file
        entries.append(entry)
    return {'config': entries, 'version': 1}


def render_persistent_net(network_state):
    ''' Given state, emit udev rules to map
        mac to ifname
    '''
    content = ""
    interfaces = network_state.get('interfaces')
    for iface in interfaces.values():
        # for physical interfaces write out a persist net udev rule
        if iface['type'] == 'physical' and \
           'name' in iface and iface.get('mac_address'):
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
        'control',
        'index',
        'inet',
        'mode',
        'name',
        'subnets',
        'type',
    ]
    if iface['type'] not in ['bond', 'bridge', 'vlan']:
        ignore_map.append('mac_address')

    for key, value in iface.items():
        if value and key not in ignore_map:
            if type(value) == list:
                value = " ".join(value)
            content += "    {} {}\n".format(key, value)

    return content


def render_route(route, indent=""):
    """ When rendering routes for an iface, in some cases applying a route
    may result in the route command returning non-zero which produces
    some confusing output for users manually using ifup/ifdown[1].  To
    that end, we will optionally include an '|| true' postfix to each
    route line allowing users to work with ifup/ifdown without using
    --force option.

    We may at somepoint not want to emit this additional postfix, and
    add a 'strict' flag to this function.  When called with strict=True,
    then we will not append the postfix.

    1. http://askubuntu.com/questions/168033/
             how-to-set-static-routes-in-ubuntu-server
    """
    content = ""
    up = indent + "post-up route add"
    down = indent + "pre-down route del"
    eol = " || true\n"
    mapping = {
        'network': '-net',
        'netmask': 'netmask',
        'gateway': 'gw',
        'metric': 'metric',
    }
    if route['network'] == '0.0.0.0' and route['netmask'] == '0.0.0.0':
        default_gw = " default gw %s" % route['gateway']
        content += up + default_gw + eol
        content += down + default_gw + eol
    elif route['network'] == '::' and route['netmask'] == 0:
        # ipv6!
        default_gw = " -A inet6 default gw %s" % route['gateway']
        content += up + default_gw + eol
        content += down + default_gw + eol
    else:
        route_line = ""
        for k in ['network', 'netmask', 'gateway', 'metric']:
            if k in route:
                route_line += " %s %s" % (mapping[k], route[k])
        content += up + route_line + eol
        content += down + route_line + eol

    return content


def iface_start_entry(iface, index):
    fullname = iface['name']
    if index != 0:
        fullname += ":%s" % index

    control = iface['control']
    if control == "auto":
        cverb = "auto"
    elif control in ("hotplug",):
        cverb = "allow-" + control
    else:
        cverb = "# control-" + control

    subst = iface.copy()
    subst.update({'fullname': fullname, 'cverb': cverb})

    return ("{cverb} {fullname}\n"
            "iface {fullname} {inet} {mode}\n").format(**subst)


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

        if content[-2:] != "\n\n":
            content += "\n"
        subnets = iface.get('subnets', {})
        if subnets:
            for index, subnet in zip(range(0, len(subnets)), subnets):
                if content[-2:] != "\n\n":
                    content += "\n"
                iface['index'] = index
                iface['mode'] = subnet['type']
                iface['control'] = subnet.get('control', 'auto')
                if iface['mode'].endswith('6'):
                    iface['inet'] += '6'
                elif iface['mode'] == 'static' and ":" in subnet['address']:
                    iface['inet'] += '6'
                if iface['mode'].startswith('dhcp'):
                    iface['mode'] = 'dhcp'

                content += iface_start_entry(iface, index)
                content += iface_add_subnet(iface, subnet)
                content += iface_add_attrs(iface)
        else:
            # ifenslave docs say to auto the slave devices
            if 'bond-master' in iface:
                content += "auto {name}\n".format(**iface)
            content += "iface {name} {inet} {mode}\n".format(**iface)
            content += iface_add_attrs(iface)

    for route in network_state.get('routes'):
        content += render_route(route)

    # global replacements until v2 format
    content = content.replace('mac_address', 'hwaddress')
    return content


def render_network_state(target, network_state, eni="etc/network/interfaces",
                         links_prefix=LINKS_FNAME_PREFIX,
                         netrules='etc/udev/rules.d/70-persistent-net.rules'):

    fpeni = os.path.sep.join((target, eni,))
    util.ensure_dir(os.path.dirname(fpeni))
    with open(fpeni, 'w+') as f:
        f.write(render_interfaces(network_state))

    if netrules:
        netrules = os.path.sep.join((target, netrules,))
        util.ensure_dir(os.path.dirname(netrules))
        with open(netrules, 'w+') as f:
            f.write(render_persistent_net(network_state))

    if links_prefix:
        render_systemd_links(target, network_state, links_prefix)


def render_systemd_links(target, network_state,
                         links_prefix=LINKS_FNAME_PREFIX):
    fp_prefix = os.path.sep.join((target, links_prefix))
    for f in glob.glob(fp_prefix + "*"):
        os.unlink(f)

    interfaces = network_state.get('interfaces')
    for iface in interfaces.values():
        if (iface['type'] == 'physical' and 'name' in iface and
                iface.get('mac_address')):
            fname = fp_prefix + iface['name'] + ".link"
            with open(fname, "w") as fp:
                fp.write("\n".join([
                    "[Match]",
                    "MACAddress=" + iface['mac_address'],
                    "",
                    "[Link]",
                    "Name=" + iface['name'],
                    ""
                ]))


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

    if 'ip=' not in cmdline:
        return None

    if mac_addrs is None:
        mac_addrs = {k: sys_netdev_info(k, 'address')
                     for k in get_devicelist()}

    return config_from_klibc_net_cfg(files=files, mac_addrs=mac_addrs)


# vi: ts=4 expandtab syntax=python
