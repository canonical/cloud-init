# This file is part of cloud-init. See LICENSE file for license information.

import copy
import glob
import os
import re

from . import ParserError

from . import renderer

from cloudinit import util


NET_CONFIG_COMMANDS = [
    "pre-up", "up", "post-up", "down", "pre-down", "post-down",
]

NET_CONFIG_BRIDGE_OPTIONS = [
    "bridge_ageing", "bridge_bridgeprio", "bridge_fd", "bridge_gcinit",
    "bridge_hello", "bridge_maxage", "bridge_maxwait", "bridge_stp",
]

NET_CONFIG_OPTIONS = [
    "address", "netmask", "broadcast", "network", "metric", "gateway",
    "pointtopoint", "media", "mtu", "hostname", "leasehours", "leasetime",
    "vendor", "client", "bootfile", "server", "hwaddr", "provider", "frame",
    "netnum", "endpoint", "local", "ttl",
]


# TODO: switch valid_map based on mode inet/inet6
def _iface_add_subnet(iface, subnet):
    content = []
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
            content.append("    {0} {1}".format(key, value))

    return sorted(content)


# TODO: switch to valid_map for attrs
def _iface_add_attrs(iface, index):
    # If the index is non-zero, this is an alias interface. Alias interfaces
    # represent additional interface addresses, and should not have additional
    # attributes. (extra attributes here are almost always either incorrect,
    # or are applied to the parent interface.) So if this is an alias, stop
    # right here.
    if index != 0:
        return []
    content = []
    ignore_map = [
        'control',
        'index',
        'inet',
        'mode',
        'name',
        'subnets',
        'type',
    ]
    renames = {'mac_address': 'hwaddress'}
    if iface['type'] not in ['bond', 'bridge', 'vlan']:
        ignore_map.append('mac_address')

    for key, value in iface.items():
        if not value or key in ignore_map:
            continue
        if type(value) == list:
            value = " ".join(value)
        content.append("    {0} {1}".format(renames.get(key, key), value))

    return sorted(content)


def _iface_start_entry(iface, index, render_hwaddress=False):
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

    lines = [
        "{cverb} {fullname}".format(**subst),
        "iface {fullname} {inet} {mode}".format(**subst)]
    if render_hwaddress and iface.get('mac_address'):
        lines.append("    hwaddress {mac_address}".format(**subst))

    return lines


def _parse_deb_config_data(ifaces, contents, src_dir, src_path):
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
                    _parse_deb_config_data(
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
                _parse_deb_config_data(
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
            if split[1] == "ether":
                val = split[2]
            else:
                val = split[1]
            ifaces[currif]['hwaddress'] = val
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
    _parse_deb_config_data(
        ifaces, contents,
        os.path.dirname(abs_path), abs_path)
    return ifaces


def convert_eni_data(eni_data):
    # return a network config representation of what is in eni_data
    ifaces = {}
    _parse_deb_config_data(ifaces, eni_data, src_dir=None, src_path=None)
    return _ifaces_to_net_config_data(ifaces)


def _ifaces_to_net_config_data(ifaces):
    """Return network config that represents the ifaces data provided.
    ifaces = parse_deb_config("/etc/network/interfaces")
    config = ifaces_to_net_config_data(ifaces)
    state = parse_net_config_data(config)."""
    devs = {}
    for name, data in ifaces.items():
        # devname is 'eth0' for name='eth0:1'
        devname = name.partition(":")[0]
        if devname not in devs:
            devs[devname] = {'type': 'physical', 'name': devname,
                             'subnets': []}
            # this isnt strictly correct, but some might specify
            # hwaddress on a nic for matching / declaring name.
            if 'hwaddress' in data:
                devs[devname]['mac_address'] = data['hwaddress']
        subnet = {'_orig_eni_name': name, 'type': data['method']}
        if data.get('auto'):
            subnet['control'] = 'auto'
        else:
            subnet['control'] = 'manual'

        if data.get('method') == 'static':
            subnet['address'] = data['address']

        for copy_key in ('netmask', 'gateway', 'broadcast'):
            if copy_key in data:
                subnet[copy_key] = data[copy_key]

        if 'dns' in data:
            for n in ('nameservers', 'search'):
                if n in data['dns'] and data['dns'][n]:
                    subnet['dns_' + n] = data['dns'][n]
        devs[devname]['subnets'].append(subnet)

    return {'version': 1,
            'config': [devs[d] for d in sorted(devs)]}


class Renderer(renderer.Renderer):
    """Renders network information in a /etc/network/interfaces format."""

    def __init__(self, config=None):
        if not config:
            config = {}
        self.eni_path = config.get('eni_path', 'etc/network/interfaces')
        self.eni_header = config.get('eni_header', None)
        self.links_path_prefix = config.get(
            'links_path_prefix', 'etc/systemd/network/50-cloud-init-')
        self.netrules_path = config.get(
            'netrules_path', 'etc/udev/rules.d/70-persistent-net.rules')

    def _render_route(self, route, indent=""):
        """When rendering routes for an iface, in some cases applying a route
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
        content = []
        up = indent + "post-up route add"
        down = indent + "pre-down route del"
        or_true = " || true"
        mapping = {
            'network': '-net',
            'netmask': 'netmask',
            'gateway': 'gw',
            'metric': 'metric',
        }
        if route['network'] == '0.0.0.0' and route['netmask'] == '0.0.0.0':
            default_gw = " default gw %s" % route['gateway']
            content.append(up + default_gw + or_true)
            content.append(down + default_gw + or_true)
        elif route['network'] == '::' and route['netmask'] == 0:
            # ipv6!
            default_gw = " -A inet6 default gw %s" % route['gateway']
            content.append(up + default_gw + or_true)
            content.append(down + default_gw + or_true)
        else:
            route_line = ""
            for k in ['network', 'netmask', 'gateway', 'metric']:
                if k in route:
                    route_line += " %s %s" % (mapping[k], route[k])
            content.append(up + route_line + or_true)
            content.append(down + route_line + or_true)
        return content

    def _render_iface(self, iface, render_hwaddress=False):
        sections = []
        subnets = iface.get('subnets', {})
        if subnets:
            for index, subnet in zip(range(0, len(subnets)), subnets):
                iface['index'] = index
                iface['mode'] = subnet['type']
                iface['control'] = subnet.get('control', 'auto')
                subnet_inet = 'inet'
                if iface['mode'].endswith('6'):
                    # This is a request for DHCPv6.
                    subnet_inet += '6'
                elif iface['mode'] == 'static' and ":" in subnet['address']:
                    # This is a static IPv6 address.
                    subnet_inet += '6'
                iface['inet'] = subnet_inet
                if iface['mode'].startswith('dhcp'):
                    iface['mode'] = 'dhcp'

                lines = list(
                    _iface_start_entry(
                        iface, index, render_hwaddress=render_hwaddress) +
                    _iface_add_subnet(iface, subnet) +
                    _iface_add_attrs(iface, index)
                )
                for route in subnet.get('routes', []):
                    lines.extend(self._render_route(route, indent="    "))

                if len(subnets) > 1 and index == 0:
                    tmpl = "    post-up ifup %s:%s\n"
                    for i in range(1, len(subnets)):
                        lines.append(tmpl % (iface['name'], i))

                sections.append(lines)
        else:
            # ifenslave docs say to auto the slave devices
            lines = []
            if 'bond-master' in iface or 'bond-slaves' in iface:
                lines.append("auto {name}".format(**iface))
            lines.append("iface {name} {inet} {mode}".format(**iface))
            lines.extend(_iface_add_attrs(iface, index=0))
            sections.append(lines)
        return sections

    def _render_interfaces(self, network_state, render_hwaddress=False):
        '''Given state, emit etc/network/interfaces content.'''

        # handle 'lo' specifically as we need to insert the global dns entries
        # there (as that is the only interface that will be always up).
        lo = {'name': 'lo', 'type': 'physical', 'inet': 'inet',
              'subnets': [{'type': 'loopback', 'control': 'auto'}]}
        for iface in network_state.iter_interfaces():
            if iface.get('name') == "lo":
                lo = copy.deepcopy(iface)

        nameservers = network_state.dns_nameservers
        if nameservers:
            lo['subnets'][0]["dns_nameservers"] = (" ".join(nameservers))

        searchdomains = network_state.dns_searchdomains
        if searchdomains:
            lo['subnets'][0]["dns_search"] = (" ".join(searchdomains))

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

        sections = []
        sections.extend(self._render_iface(lo))
        for iface in sorted(network_state.iter_interfaces(),
                            key=lambda k: (order[k['type']], k['name'])):

            if iface.get('name') == "lo":
                continue
            sections.extend(
                self._render_iface(iface, render_hwaddress=render_hwaddress))

        for route in network_state.iter_routes():
            sections.append(self._render_route(route))

        return '\n\n'.join(['\n'.join(s) for s in sections]) + "\n"

    def render_network_state(self, target, network_state):
        fpeni = os.path.join(target, self.eni_path)
        util.ensure_dir(os.path.dirname(fpeni))
        header = self.eni_header if self.eni_header else ""
        util.write_file(fpeni, header + self._render_interfaces(network_state))

        if self.netrules_path:
            netrules = os.path.join(target, self.netrules_path)
            util.ensure_dir(os.path.dirname(netrules))
            util.write_file(netrules,
                            self._render_persistent_net(network_state))

        if self.links_path_prefix:
            self._render_systemd_links(target, network_state,
                                       links_prefix=self.links_path_prefix)

    def _render_systemd_links(self, target, network_state, links_prefix):
        fp_prefix = os.path.join(target, links_prefix)
        for f in glob.glob(fp_prefix + "*"):
            os.unlink(f)
        for iface in network_state.iter_interfaces():
            if (iface['type'] == 'physical' and 'name' in iface and
                    iface.get('mac_address')):
                fname = fp_prefix + iface['name'] + ".link"
                content = "\n".join([
                    "[Match]",
                    "MACAddress=" + iface['mac_address'],
                    "",
                    "[Link]",
                    "Name=" + iface['name'],
                    ""
                ])
                util.write_file(fname, content)


def network_state_to_eni(network_state, header=None, render_hwaddress=False):
    # render the provided network state, return a string of equivalent eni
    eni_path = 'etc/network/interfaces'
    renderer = Renderer({
        'eni_path': eni_path,
        'eni_header': header,
        'links_path_prefix': None,
        'netrules_path': None,
    })
    if not header:
        header = ""
    if not header.endswith("\n"):
        header += "\n"
    contents = renderer._render_interfaces(
        network_state, render_hwaddress=render_hwaddress)
    return header + contents

# vi: ts=4 expandtab
