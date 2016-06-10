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

import os
import re

import six

from cloudinit.distros.parsers import resolv_conf
from cloudinit import util

from . import network_state
from .udev import generate_udev_rule


def _filter_by_type(match_type):
    return lambda iface: match_type == iface['type']


def _filter_by_name(match_name):
    return lambda iface: match_name == iface['name']


_filter_by_physical = _filter_by_type('physical')


def _is_default_route(route):
    if route['network'] == '::' and route['netmask'] == 0:
        return True
    if route['network'] == '0.0.0.0' and route['netmask'] == '0.0.0.0':
        return True
    return False


def _quote_value(value):
    if re.search(r"\s", value):
        # This doesn't handle complex cases...
        if value.startswith('"') and value.endswith('"'):
            return value
        else:
            return '"%s"' % value
    else:
        return value


class NetworkStateHelper(object):
    def __init__(self, network_state):
        self._network_state = network_state.copy()

    @property
    def dns_nameservers(self):
        return self._network_state['dns']['nameservers']

    @property
    def dns_searchdomains(self):
        return self._network_state['dns']['search']

    def iter_interfaces(self, filter_func=None):
        ifaces = self._network_state.get('interfaces')
        if ifaces:
            for iface in ifaces.values():
                if filter_func is None:
                    yield iface
                else:
                    if filter_func(iface):
                        yield iface


class ConfigMap(object):
    """Sysconfig like dictionary object."""

    default_header = ('# Created by cloud-init on instance'
                      ' boot automatically, do not edit.\n#')

    # Why does redhat prefer yes/no to true/false??
    _bool_map = {
        True: 'yes',
        False: 'no',
    }

    def __init__(self):
        self._conf = {}

    def __setitem__(self, key, value):
        self._conf[key] = value

    def drop(self, key):
        self._conf.pop(key, None)

    def __len__(self):
        return len(self._conf)

    def to_string(self):
        buf = six.StringIO()
        buf.write(self.default_header)
        if self._conf:
            buf.write("\n")
        for key in sorted(self._conf.keys()):
            value = self._conf[key]
            if isinstance(value, bool):
                value = self._bool_map[value]
            if not isinstance(value, six.string_types):
                value = str(value)
            buf.write("%s=%s\n" % (key, _quote_value(value)))
        return buf.getvalue()


class Route(ConfigMap):
    """Represents a route configuration."""

    route_fn_tpl = '%(base)s/network-scripts/route-%(name)s'

    def __init__(self, route_name, base_sysconf_dir):
        super(Route, self).__init__()
        self.last_idx = 1
        self.has_set_default = False
        self._route_name = route_name
        self._base_sysconf_dir = base_sysconf_dir

    def copy(self):
        r = Route(self._route_name, self._base_sysconf_dir)
        r._conf = self._conf.copy()
        r.last_idx = self.last_idx
        r.has_set_default = self.has_set_default
        return r

    @property
    def path(self):
        return self.route_fn_tpl % ({'base': self._base_sysconf_dir,
                                     'name': self._route_name})


class NetInterface(ConfigMap):
    """Represents a sysconfig/networking-script (and its config + children)."""

    iface_fn_tpl = '%(base)s/network-scripts/ifcfg-%(name)s'

    iface_types = {
        'ethernet': 'Ethernet',
        'bond': 'Bond',
        'bridge': 'Bridge',
    }

    def __init__(self, iface_name, base_sysconf_dir, kind='ethernet'):
        super(NetInterface, self).__init__()
        self.children = []
        self.routes = Route(iface_name, base_sysconf_dir)
        self._kind = kind
        self._iface_name = iface_name
        self._conf['DEVICE'] = iface_name
        self._conf['TYPE'] = self.iface_types[kind]
        self._base_sysconf_dir = base_sysconf_dir

    @property
    def name(self):
        return self._iface_name

    @name.setter
    def name(self, iface_name):
        self._iface_name = iface_name
        self._conf['DEVICE'] = iface_name

    @property
    def kind(self):
        return self._kind

    @kind.setter
    def kind(self, kind):
        self._kind = kind
        self._conf['TYPE'] = self.iface_types[kind]

    @property
    def path(self):
        return self.iface_fn_tpl % ({'base': self._base_sysconf_dir,
                                     'name': self.name})

    def copy(self, copy_children=False, copy_routes=False):
        c = NetInterface(self.name, self._base_sysconf_dir, kind=self._kind)
        c._conf = self._conf.copy()
        if copy_children:
            c.children = list(self.children)
        if copy_routes:
            c.routes = self.routes.copy()
        return c


class Renderer(object):
    """Renders network information in a /etc/sysconfig format."""

    # See: https://access.redhat.com/documentation/en-US/\
    #      Red_Hat_Enterprise_Linux/6/html/Deployment_Guide/\
    #      s1-networkscripts-interfaces.html (or other docs for
    #                                         details about this)

    iface_defaults = tuple([
        ('ONBOOT', True),
        ('USERCTL', False),
        ('NM_CONTROLLED', False),
        ('BOOTPROTO', 'none'),
    ])

    # If these keys exist, then there values will be used to form
    # a BONDING_OPTS grouping; otherwise no grouping will be set.
    bond_tpl_opts = tuple([
        ('bond_mode', "mode=%s"),
        ('bond_xmit_hash_policy', "xmit_hash_policy=%s"),
        ('bond_miimon', "miimon=%s"),
    ])

    bridge_opts_keys = tuple([
        ('bridge_stp', 'STP'),
        ('bridge_ageing', 'AGEING'),
        ('bridge_bridgeprio', 'PRIO'),
    ])

    @staticmethod
    def _render_persistent_net(network_state):
        """Given state, emit udev rules to map mac to ifname."""
        # TODO(harlowja): this seems shared between eni renderer and
        # this, so move it to a shared location.
        content = six.StringIO()
        for iface in network_state.iter_interfaces(_filter_by_physical):
            # for physical interfaces write out a persist net udev rule
            if 'name' in iface and iface.get('mac_address'):
                content.write(generate_udev_rule(iface['name'],
                                                 iface['mac_address']))
        return content.getvalue()

    @classmethod
    def _render_iface_shared(cls, iface, iface_cfg):
        for k, v in cls.iface_defaults:
            iface_cfg[k] = v
        for (old_key, new_key) in [('mac_address', 'HWADDR'), ('mtu', 'MTU')]:
            old_value = iface.get(old_key)
            if old_value is not None:
                iface_cfg[new_key] = old_value

    @classmethod
    def _render_subnet(cls, iface_cfg, route_cfg, subnet):
        subnet_type = subnet.get('type')
        if subnet_type == 'dhcp6':
            iface_cfg['DHCPV6C'] = True
            iface_cfg['IPV6INIT'] = True
            iface_cfg['BOOTPROTO'] = 'dhcp'
        elif subnet_type in ['dhcp4', 'dhcp']:
            iface_cfg['BOOTPROTO'] = 'dhcp'
        elif subnet_type == 'static':
            iface_cfg['BOOTPROTO'] = 'static'
            if subnet.get('ipv6'):
                iface_cfg['IPV6ADDR'] = subnet['address']
                iface_cfg['IPV6INIT'] = True
            else:
                iface_cfg['IPADDR'] = subnet['address']
        else:
            raise ValueError("Unknown subnet type '%s' found"
                             " for interface '%s'" % (subnet_type,
                                                      iface_cfg.name))
        if 'netmask' in subnet:
            iface_cfg['NETMASK'] = subnet['netmask']
        for route in subnet.get('routes', []):
            if _is_default_route(route):
                if route_cfg.has_set_default:
                    raise ValueError("Duplicate declaration of default"
                                     " route found for interface '%s'"
                                     % (iface_cfg.name))
                # NOTE(harlowja): ipv6 and ipv4 default gateways
                gw_key = 'GATEWAY0'
                nm_key = 'NETMASK0'
                addr_key = 'ADDRESS0'
                # The owning interface provides the default route.
                #
                # TODO(harlowja): add validation that no other iface has
                # also provided the default route?
                iface_cfg['DEFROUTE'] = True
                if 'gateway' in route:
                    iface_cfg['GATEWAY'] = route['gateway']
                route_cfg.has_set_default = True
            else:
                gw_key = 'GATEWAY%s' % route_cfg.last_idx
                nm_key = 'NETMASK%s' % route_cfg.last_idx
                addr_key = 'ADDRESS%s' % route_cfg.last_idx
                route_cfg.last_idx += 1
            for (old_key, new_key) in [('gateway', gw_key),
                                       ('netmask', nm_key),
                                       ('network', addr_key)]:
                if old_key in route:
                    route_cfg[new_key] = route[old_key]

    @classmethod
    def _render_bonding_opts(cls, iface_cfg, iface):
        bond_opts = []
        for (bond_key, value_tpl) in cls.bond_tpl_opts:
            # Seems like either dash or underscore is possible?
            bond_keys = [bond_key, bond_key.replace("_", "-")]
            for bond_key in bond_keys:
                if bond_key in iface:
                    bond_value = iface[bond_key]
                    if isinstance(bond_value, (tuple, list)):
                        bond_value = " ".join(bond_value)
                    bond_opts.append(value_tpl % (bond_value))
                    break
        if bond_opts:
            iface_cfg['BONDING_OPTS'] = " ".join(bond_opts)

    @classmethod
    def _render_physical_interfaces(cls, network_state, iface_contents):
        for iface in network_state.iter_interfaces(_filter_by_physical):
            iface_name = iface['name']
            iface_subnets = iface.get("subnets", [])
            iface_cfg = iface_contents[iface_name]
            route_cfg = iface_cfg.routes
            if len(iface_subnets) == 1:
                cls._render_subnet(iface_cfg, route_cfg, iface_subnets[0])
            elif len(iface_subnets) > 1:
                for i, iface_subnet in enumerate(iface_subnets,
                                                 start=len(iface.children)):
                    iface_sub_cfg = iface_cfg.copy()
                    iface_sub_cfg.name = "%s:%s" % (iface_name, i)
                    iface.children.append(iface_sub_cfg)
                    cls._render_subnet(iface_sub_cfg, route_cfg, iface_subnet)

    @classmethod
    def _render_bond_interfaces(cls, network_state, iface_contents):
        for iface in network_state.iter_interfaces(_filter_by_type('bond')):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            cls._render_bonding_opts(iface_cfg, iface)
            iface_master_name = iface['bond-master']
            iface_cfg['MASTER'] = iface_master_name
            iface_cfg['SLAVE'] = True
            # Ensure that the master interface (and any of its children)
            # are actually marked as being bond types...
            master_cfg = iface_contents[iface_master_name]
            master_cfgs = [master_cfg]
            master_cfgs.extend(master_cfg.children)
            for master_cfg in master_cfgs:
                master_cfg['BONDING_MASTER'] = True
                master_cfg.kind = 'bond'

    @staticmethod
    def _render_vlan_interfaces(network_state, iface_contents):
        for iface in network_state.iter_interfaces(_filter_by_type('vlan')):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            iface_cfg['VLAN'] = True
            iface_cfg['PHYSDEV'] = iface_name[:iface_name.rfind('.')]

    @staticmethod
    def _render_dns(network_state, existing_dns_path=None):
        content = resolv_conf.ResolvConf("")
        if existing_dns_path and os.path.isfile(existing_dns_path):
            content = resolv_conf.ResolvConf(util.load_file(existing_dns_path))
        for ns in network_state.dns_nameservers:
            content.add_nameserver(ns)
        for d in network_state.dns_searchdomains:
            content.add_search_domain(d)
        return str(content)

    @classmethod
    def _render_bridge_interfaces(cls, network_state, iface_contents):
        for iface in network_state.iter_interfaces(_filter_by_type('bridge')):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            iface_cfg.kind = 'bridge'
            for old_key, new_key in cls.bridge_opts_keys:
                if old_key in iface:
                    iface_cfg[new_key] = iface[old_key]
            # Is this the right key to get all the connected interfaces?
            for bridged_iface_name in iface.get('bridge_ports', []):
                # Ensure all bridged interfaces are correctly tagged
                # as being bridged to this interface.
                bridged_cfg = iface_contents[bridged_iface_name]
                bridged_cfgs = [bridged_cfg]
                bridged_cfgs.extend(bridged_cfg.children)
                for bridge_cfg in bridged_cfgs:
                    bridge_cfg['BRIDGE'] = iface_name

    @classmethod
    def _render_sysconfig(cls, base_sysconf_dir, network_state):
        '''Given state, return /etc/sysconfig files + contents'''
        iface_contents = {}
        for iface in network_state.iter_interfaces():
            iface_name = iface['name']
            iface_cfg = NetInterface(iface_name, base_sysconf_dir)
            cls._render_iface_shared(iface, iface_cfg)
            iface_contents[iface_name] = iface_cfg
        cls._render_physical_interfaces(network_state, iface_contents)
        cls._render_bond_interfaces(network_state, iface_contents)
        cls._render_vlan_interfaces(network_state, iface_contents)
        cls._render_bridge_interfaces(network_state, iface_contents)
        contents = {}
        for iface_name, iface_cfg in iface_contents.items():
            if iface_cfg or iface_cfg.children:
                contents[iface_cfg.path] = iface_cfg.to_string()
                for iface_cfg in iface_cfg.children:
                    if iface_cfg:
                        contents[iface_cfg.path] = iface_cfg.to_string()
            if iface_cfg.routes:
                contents[iface_cfg.routes.path] = iface_cfg.routes.to_string()
        return contents

    def render_network_state(
            self, target, network_state, sysconf_dir="etc/sysconfig/",
            netrules='etc/udev/rules.d/70-persistent-net.rules',
            dns='etc/resolv.conf'):
        network_state = NetworkStateHelper(network_state)
        if target:
            base_sysconf_dir = os.path.join(target, sysconf_dir)
        else:
            base_sysconf_dir = sysconf_dir
        for path, data in self._render_sysconfig(base_sysconf_dir,
                                                 network_state).items():
            if target:
                util.write_file(path, data)
            else:
                print("File to be at: %s" % path)
                print(data)
        if dns:
            if target:
                dns_path = os.path.join(target, dns)
                resolv_content = self._render_dns(network_state,
                                                  existing_dns_path=dns_path)
                util.write_file(dns_path, resolv_content)
            else:
                resolv_content = self._render_dns(network_state)
                dns_path = dns
                print("File to be at: %s" % dns_path)
                print(resolv_content)
        if netrules:
            netrules_content = self._render_persistent_net(network_state)
            if target:
                netrules_path = os.path.join(target, netrules)
                util.write_file(netrules_path, netrules_content)
            else:
                netrules_path = netrules
                print("File to be at: %s" % netrules_path)
                print(netrules_content)


def main():
    """Reads a os network state json file and outputs what would be written."""
    from cloudinit.sources.helpers import openstack

    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", metavar="FILE",
                        help=("openstack network json file"
                              " to read (required)"),
                        required=True)
    parser.add_argument("-d", "--dir", metavar="DIR",
                        help=("directory to write output into (if"
                              " not provided then written to stdout)"),
                        default=None)
    args = parser.parse_args()

    network_json = json.loads(util.load_file(args.file))
    net_state = network_state.parse_net_config_data(
        openstack.convert_net_json(network_json), skip_broken=False)
    r = Renderer()
    r.render_network_state(args.dir, NetworkStateHelper(net_state))


if __name__ == '__main__':
    main()
