# vi: ts=4 expandtab
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

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
            content += "    {0} {1}\n".format(key, value)

    return content


# TODO: switch to valid_map for attrs

def _iface_add_attrs(iface):
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
            content += "    {0} {1}\n".format(key, value)

    return content


def _iface_start_entry(iface, index):
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
        if devname == "lo":
            # currently provding 'lo' in network config results in duplicate
            # entries. in rendered interfaces file. so skip it.
            continue
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

    def _render_interfaces(self, network_state, render_hwaddress=False):
        '''Given state, emit etc/network/interfaces content.'''

        content = ""
        content += "auto lo\niface lo inet loopback\n"

        nameservers = network_state.dns_nameservers
        if nameservers:
            content += "    dns-nameservers %s\n" % (" ".join(nameservers))
        searchdomains = network_state.dns_searchdomains
        if searchdomains:
            content += "    dns-search %s\n" % (" ".join(searchdomains))

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
        for iface in sorted(network_state.iter_interfaces(),
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
                    elif (iface['mode'] == 'static' and
                          ":" in subnet['address']):
                        iface['inet'] += '6'
                    if iface['mode'].startswith('dhcp'):
                        iface['mode'] = 'dhcp'

                    content += _iface_start_entry(iface, index)
                    if render_hwaddress and iface.get('mac_address'):
                        content += "    hwaddress %s" % iface['mac_address']
                    content += _iface_add_subnet(iface, subnet)
                    content += _iface_add_attrs(iface)
                    for route in subnet.get('routes', []):
                        content += self._render_route(route, indent="    ")
            else:
                # ifenslave docs say to auto the slave devices
                if 'bond-master' in iface:
                    content += "auto {name}\n".format(**iface)
                content += "iface {name} {inet} {mode}\n".format(**iface)
                content += _iface_add_attrs(iface)

        for route in network_state.iter_routes():
            content += self._render_route(route)

        return content

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
