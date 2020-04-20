# This file is part of cloud-init. See LICENSE file for license information.

import copy
import io
import os
import re

from configobj import ConfigObj

from cloudinit import log as logging
from cloudinit import util
from cloudinit.distros.parsers import networkmanager_conf
from cloudinit.distros.parsers import resolv_conf

from . import renderer
from .network_state import (
    is_ipv6_addr, net_prefix_to_ipv4_mask, subnet_is_ipv6, IPV6_DYNAMIC_TYPES)

LOG = logging.getLogger(__name__)
NM_CFG_FILE = "/etc/NetworkManager/NetworkManager.conf"
KNOWN_DISTROS = ['centos', 'fedora', 'rhel', 'suse']


def _make_header(sep='#'):
    lines = [
        "Created by cloud-init on instance boot automatically, do not edit.",
        "",
    ]
    for i in range(0, len(lines)):
        if lines[i]:
            lines[i] = sep + " " + lines[i]
        else:
            lines[i] = sep
    return "\n".join(lines)


def _is_default_route(route):
    default_nets = ('::', '0.0.0.0')
    return route['prefix'] == 0 and route['network'] in default_nets


def _quote_value(value):
    if re.search(r"\s", value):
        # This doesn't handle complex cases...
        if value.startswith('"') and value.endswith('"'):
            return value
        else:
            return '"%s"' % value
    else:
        return value


def enable_ifcfg_rh(path):
    """Add ifcfg-rh to NetworkManager.cfg plugins if main section is present"""
    config = ConfigObj(path)
    if 'main' in config:
        if 'plugins' in config['main']:
            if 'ifcfg-rh' in config['main']['plugins']:
                return
        else:
            config['main']['plugins'] = []

        if isinstance(config['main']['plugins'], list):
            config['main']['plugins'].append('ifcfg-rh')
        else:
            config['main']['plugins'] = [config['main']['plugins'], 'ifcfg-rh']
        config.write()
        LOG.debug('Enabled ifcfg-rh NetworkManager plugins')


class ConfigMap(object):
    """Sysconfig like dictionary object."""

    # Why does redhat prefer yes/no to true/false??
    _bool_map = {
        True: 'yes',
        False: 'no',
    }

    def __init__(self):
        self._conf = {}

    def __setitem__(self, key, value):
        self._conf[key] = value

    def __getitem__(self, key):
        return self._conf[key]

    def get(self, key):
        return self._conf.get(key)

    def __contains__(self, key):
        return key in self._conf

    def drop(self, key):
        self._conf.pop(key, None)

    def __len__(self):
        return len(self._conf)

    def to_string(self):
        buf = io.StringIO()
        buf.write(_make_header())
        if self._conf:
            buf.write("\n")
        for key in sorted(self._conf.keys()):
            value = self._conf[key]
            if isinstance(value, bool):
                value = self._bool_map[value]
            if not isinstance(value, str):
                value = str(value)
            buf.write("%s=%s\n" % (key, _quote_value(value)))
        return buf.getvalue()

    def update(self, updates):
        self._conf.update(updates)


class Route(ConfigMap):
    """Represents a route configuration."""

    def __init__(self, route_name, base_sysconf_dir,
                 ipv4_tpl, ipv6_tpl):
        super(Route, self).__init__()
        self.last_idx = 1
        self.has_set_default_ipv4 = False
        self.has_set_default_ipv6 = False
        self._route_name = route_name
        self._base_sysconf_dir = base_sysconf_dir
        self.route_fn_tpl_ipv4 = ipv4_tpl
        self.route_fn_tpl_ipv6 = ipv6_tpl

    def copy(self):
        r = Route(self._route_name, self._base_sysconf_dir,
                  self.route_fn_tpl_ipv4, self.route_fn_tpl_ipv6)
        r._conf = self._conf.copy()
        r.last_idx = self.last_idx
        r.has_set_default_ipv4 = self.has_set_default_ipv4
        r.has_set_default_ipv6 = self.has_set_default_ipv6
        return r

    @property
    def path_ipv4(self):
        return self.route_fn_tpl_ipv4 % ({'base': self._base_sysconf_dir,
                                          'name': self._route_name})

    @property
    def path_ipv6(self):
        return self.route_fn_tpl_ipv6 % ({'base': self._base_sysconf_dir,
                                          'name': self._route_name})

    def is_ipv6_route(self, address):
        return ':' in address

    def to_string(self, proto="ipv4"):
        # only accept ipv4 and ipv6
        if proto not in ['ipv4', 'ipv6']:
            raise ValueError("Unknown protocol '%s'" % (str(proto)))
        buf = io.StringIO()
        buf.write(_make_header())
        if self._conf:
            buf.write("\n")
        # need to reindex IPv4 addresses
        # (because Route can contain a mix of IPv4 and IPv6)
        reindex = -1
        for key in sorted(self._conf.keys()):
            if 'ADDRESS' in key:
                index = key.replace('ADDRESS', '')
                address_value = str(self._conf[key])
                # only accept combinations:
                # if proto ipv6 only display ipv6 routes
                # if proto ipv4 only display ipv4 routes
                # do not add ipv6 routes if proto is ipv4
                # do not add ipv4 routes if proto is ipv6
                # (this array will contain a mix of ipv4 and ipv6)
                if proto == "ipv4" and not self.is_ipv6_route(address_value):
                    netmask_value = str(self._conf['NETMASK' + index])
                    gateway_value = str(self._conf['GATEWAY' + index])
                    # increase IPv4 index
                    reindex = reindex + 1
                    buf.write("%s=%s\n" % ('ADDRESS' + str(reindex),
                                           _quote_value(address_value)))
                    buf.write("%s=%s\n" % ('GATEWAY' + str(reindex),
                                           _quote_value(gateway_value)))
                    buf.write("%s=%s\n" % ('NETMASK' + str(reindex),
                                           _quote_value(netmask_value)))
                    metric_key = 'METRIC' + index
                    if metric_key in self._conf:
                        metric_value = str(self._conf['METRIC' + index])
                        buf.write("%s=%s\n" % ('METRIC' + str(reindex),
                                               _quote_value(metric_value)))
                elif proto == "ipv6" and self.is_ipv6_route(address_value):
                    netmask_value = str(self._conf['NETMASK' + index])
                    gateway_value = str(self._conf['GATEWAY' + index])
                    metric_value = (
                        'metric ' + str(self._conf['METRIC' + index])
                        if 'METRIC' + index in self._conf else '')
                    buf.write(
                        "%s/%s via %s %s dev %s\n" % (address_value,
                                                      netmask_value,
                                                      gateway_value,
                                                      metric_value,
                                                      self._route_name))

        return buf.getvalue()


class NetInterface(ConfigMap):
    """Represents a sysconfig/networking-script (and its config + children)."""

    iface_types = {
        'ethernet': 'Ethernet',
        'bond': 'Bond',
        'bridge': 'Bridge',
        'infiniband': 'InfiniBand',
    }

    def __init__(self, iface_name, base_sysconf_dir, templates,
                 kind='ethernet'):
        super(NetInterface, self).__init__()
        self.children = []
        self.templates = templates
        route_tpl = self.templates.get('route_templates')
        self.routes = Route(iface_name, base_sysconf_dir,
                            ipv4_tpl=route_tpl.get('ipv4'),
                            ipv6_tpl=route_tpl.get('ipv6'))
        self.iface_fn_tpl = self.templates.get('iface_templates')
        self.kind = kind

        self._iface_name = iface_name
        self._conf['DEVICE'] = iface_name
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
        if kind not in self.iface_types:
            raise ValueError(kind)
        self._kind = kind
        self._conf['TYPE'] = self.iface_types[kind]

    @property
    def path(self):
        return self.iface_fn_tpl % ({'base': self._base_sysconf_dir,
                                     'name': self.name})

    def copy(self, copy_children=False, copy_routes=False):
        c = NetInterface(self.name, self._base_sysconf_dir,
                         self.templates, kind=self._kind)
        c._conf = self._conf.copy()
        if copy_children:
            c.children = list(self.children)
        if copy_routes:
            c.routes = self.routes.copy()
        return c


class Renderer(renderer.Renderer):
    """Renders network information in a /etc/sysconfig format."""

    # See: https://access.redhat.com/documentation/en-US/\
    #      Red_Hat_Enterprise_Linux/6/html/Deployment_Guide/\
    #      s1-networkscripts-interfaces.html (or other docs for
    #                                         details about this)

    iface_defaults = {
        'rhel': {'ONBOOT': True, 'USERCTL': False, 'NM_CONTROLLED': False,
                 'BOOTPROTO': 'none'},
        'suse': {'BOOTPROTO': 'static', 'STARTMODE': 'auto'},
    }

    cfg_key_maps = {
        'rhel': {
            'accept-ra': 'IPV6_FORCE_ACCEPT_RA',
            'bridge_stp': 'STP',
            'bridge_ageing': 'AGEING',
            'bridge_bridgeprio': 'PRIO',
            'mac_address': 'HWADDR',
            'mtu': 'MTU',
        },
        'suse': {
            'bridge_stp': 'BRIDGE_STP',
            'bridge_ageing': 'BRIDGE_AGEINGTIME',
            'bridge_bridgeprio': 'BRIDGE_PRIORITY',
            'mac_address': 'LLADDR',
            'mtu': 'MTU',
        },
    }

    # If these keys exist, then their values will be used to form
    # a BONDING_OPTS grouping; otherwise no grouping will be set.
    bond_tpl_opts = tuple([
        ('bond_mode', "mode=%s"),
        ('bond_xmit_hash_policy', "xmit_hash_policy=%s"),
        ('bond_miimon', "miimon=%s"),
        ('bond_min_links', "min_links=%s"),
        ('bond_arp_interval', "arp_interval=%s"),
        ('bond_arp_ip_target', "arp_ip_target=%s"),
        ('bond_arp_validate', "arp_validate=%s"),
        ('bond_ad_select', "ad_select=%s"),
        ('bond_num_grat_arp', "num_grat_arp=%s"),
        ('bond_downdelay', "downdelay=%s"),
        ('bond_updelay', "updelay=%s"),
        ('bond_lacp_rate', "lacp_rate=%s"),
        ('bond_fail_over_mac', "fail_over_mac=%s"),
        ('bond_primary', "primary=%s"),
        ('bond_primary_reselect', "primary_reselect=%s"),
    ])

    templates = {}

    def __init__(self, config=None):
        if not config:
            config = {}
        self.sysconf_dir = config.get('sysconf_dir', 'etc/sysconfig')
        self.netrules_path = config.get(
            'netrules_path', 'etc/udev/rules.d/70-persistent-net.rules')
        self.dns_path = config.get('dns_path', 'etc/resolv.conf')
        nm_conf_path = 'etc/NetworkManager/conf.d/99-cloud-init.conf'
        self.networkmanager_conf_path = config.get('networkmanager_conf_path',
                                                   nm_conf_path)
        self.templates = {
            'control': config.get('control'),
            'iface_templates': config.get('iface_templates'),
            'route_templates': config.get('route_templates'),
        }
        self.flavor = config.get('flavor', 'rhel')

    @classmethod
    def _render_iface_shared(cls, iface, iface_cfg, flavor):
        flavor_defaults = copy.deepcopy(cls.iface_defaults.get(flavor, {}))
        iface_cfg.update(flavor_defaults)

        for old_key in ('mac_address', 'mtu', 'accept-ra'):
            old_value = iface.get(old_key)
            if old_value is not None:
                # only set HWADDR on physical interfaces
                if (old_key == 'mac_address' and
                   iface['type'] not in ['physical', 'infiniband']):
                    continue
                new_key = cls.cfg_key_maps[flavor].get(old_key)
                if new_key:
                    iface_cfg[new_key] = old_value

    @classmethod
    def _render_subnets(cls, iface_cfg, subnets, has_default_route, flavor):
        # setting base values
        if flavor == 'suse':
            iface_cfg['BOOTPROTO'] = 'static'
            if 'BRIDGE' in iface_cfg:
                iface_cfg['BOOTPROTO'] = 'dhcp'
                iface_cfg.drop('BRIDGE')
        else:
            iface_cfg['BOOTPROTO'] = 'none'

        # modifying base values according to subnets
        for i, subnet in enumerate(subnets, start=len(iface_cfg.children)):
            mtu_key = 'MTU'
            subnet_type = subnet.get('type')
            if subnet_type == 'dhcp6' or subnet_type == 'ipv6_dhcpv6-stateful':
                if flavor == 'suse':
                    # User wants dhcp for both protocols
                    if iface_cfg['BOOTPROTO'] == 'dhcp4':
                        iface_cfg['BOOTPROTO'] = 'dhcp'
                    else:
                        # Only IPv6 is DHCP, IPv4 may be static
                        iface_cfg['BOOTPROTO'] = 'dhcp6'
                    iface_cfg['DHCLIENT6_MODE'] = 'managed'
                else:
                    iface_cfg['IPV6INIT'] = True
                    # Configure network settings using DHCPv6
                    iface_cfg['DHCPV6C'] = True
            elif subnet_type == 'ipv6_dhcpv6-stateless':
                if flavor == 'suse':
                    # User wants dhcp for both protocols
                    if iface_cfg['BOOTPROTO'] == 'dhcp4':
                        iface_cfg['BOOTPROTO'] = 'dhcp'
                    else:
                        # Only IPv6 is DHCP, IPv4 may be static
                        iface_cfg['BOOTPROTO'] = 'dhcp6'
                    iface_cfg['DHCLIENT6_MODE'] = 'info'
                else:
                    iface_cfg['IPV6INIT'] = True
                    # Configure network settings using SLAAC from RAs and
                    # optional info from dhcp server using DHCPv6
                    iface_cfg['IPV6_AUTOCONF'] = True
                    iface_cfg['DHCPV6C'] = True
                    # Use Information-request to get only stateless
                    # configuration parameters (i.e., without address).
                    iface_cfg['DHCPV6C_OPTIONS'] = '-S'
            elif subnet_type == 'ipv6_slaac':
                if flavor == 'suse':
                    # User wants dhcp for both protocols
                    if iface_cfg['BOOTPROTO'] == 'dhcp4':
                        iface_cfg['BOOTPROTO'] = 'dhcp'
                    else:
                        # Only IPv6 is DHCP, IPv4 may be static
                        iface_cfg['BOOTPROTO'] = 'dhcp6'
                    iface_cfg['DHCLIENT6_MODE'] = 'info'
                else:
                    iface_cfg['IPV6INIT'] = True
                    # Configure network settings using SLAAC from RAs
                    iface_cfg['IPV6_AUTOCONF'] = True
            elif subnet_type in ['dhcp4', 'dhcp']:
                bootproto_in = iface_cfg['BOOTPROTO']
                iface_cfg['BOOTPROTO'] = 'dhcp'
                if flavor == 'suse' and subnet_type == 'dhcp4':
                    # If dhcp6 is already specified the user wants dhcp
                    # for both protocols
                    if bootproto_in != 'dhcp6':
                        # Only IPv4 is DHCP, IPv6 may be static
                        iface_cfg['BOOTPROTO'] = 'dhcp4'
            elif subnet_type in ['static', 'static6']:
                # RH info
                # grep BOOTPROTO sysconfig.txt -A2 | head -3
                # BOOTPROTO=none|bootp|dhcp
                # 'bootp' or 'dhcp' cause a DHCP client
                # to run on the device. Any other
                # value causes any static configuration
                # in the file to be applied.
                if subnet_is_ipv6(subnet) and flavor != 'suse':
                    mtu_key = 'IPV6_MTU'
                    iface_cfg['IPV6INIT'] = True
                if 'mtu' in subnet:
                    mtu_mismatch = bool(mtu_key in iface_cfg and
                                        subnet['mtu'] != iface_cfg[mtu_key])
                    if mtu_mismatch:
                        LOG.warning(
                            'Network config: ignoring %s device-level mtu:%s'
                            ' because ipv4 subnet-level mtu:%s provided.',
                            iface_cfg.name, iface_cfg[mtu_key], subnet['mtu'])
                    if subnet_is_ipv6(subnet):
                        if flavor == 'suse':
                            # TODO(rjschwei) write mtu setting to
                            # /etc/sysctl.d/
                            pass
                        else:
                            iface_cfg[mtu_key] = subnet['mtu']
                    else:
                        iface_cfg[mtu_key] = subnet['mtu']
            elif subnet_type == 'manual':
                if flavor == 'suse':
                    LOG.debug('Unknown subnet type setting "%s"', subnet_type)
                else:
                    # If the subnet has an MTU setting, then ONBOOT=True
                    # to apply the setting
                    iface_cfg['ONBOOT'] = mtu_key in iface_cfg
            else:
                raise ValueError("Unknown subnet type '%s' found"
                                 " for interface '%s'" % (subnet_type,
                                                          iface_cfg.name))
            if subnet.get('control') == 'manual':
                if flavor == 'suse':
                    iface_cfg['STARTMODE'] = 'manual'
                else:
                    iface_cfg['ONBOOT'] = False

        # set IPv4 and IPv6 static addresses
        ipv4_index = -1
        ipv6_index = -1
        for i, subnet in enumerate(subnets, start=len(iface_cfg.children)):
            subnet_type = subnet.get('type')
            # metric may apply to both dhcp and static config
            if 'metric' in subnet:
                if flavor != 'suse':
                    iface_cfg['METRIC'] = subnet['metric']
            if subnet_type in ['dhcp', 'dhcp4']:
                # On SUSE distros 'DHCLIENT_SET_DEFAULT_ROUTE' is a global
                # setting in /etc/sysconfig/network/dhcp
                if flavor != 'suse':
                    if has_default_route and iface_cfg['BOOTPROTO'] != 'none':
                        iface_cfg['DHCLIENT_SET_DEFAULT_ROUTE'] = False
                continue
            elif subnet_type in IPV6_DYNAMIC_TYPES:
                continue
            elif subnet_type in ['static', 'static6']:
                if subnet_is_ipv6(subnet):
                    ipv6_index = ipv6_index + 1
                    ipv6_cidr = "%s/%s" % (subnet['address'], subnet['prefix'])
                    if ipv6_index == 0:
                        if flavor == 'suse':
                            iface_cfg['IPADDR6'] = ipv6_cidr
                        else:
                            iface_cfg['IPV6ADDR'] = ipv6_cidr
                    elif ipv6_index == 1:
                        if flavor == 'suse':
                            iface_cfg['IPADDR6_1'] = ipv6_cidr
                        else:
                            iface_cfg['IPV6ADDR_SECONDARIES'] = ipv6_cidr
                    else:
                        if flavor == 'suse':
                            iface_cfg['IPADDR6_%d' % ipv6_index] = ipv6_cidr
                        else:
                            iface_cfg['IPV6ADDR_SECONDARIES'] += \
                                                        " " + ipv6_cidr
                else:
                    ipv4_index = ipv4_index + 1
                    suff = "" if ipv4_index == 0 else str(ipv4_index)
                    iface_cfg['IPADDR' + suff] = subnet['address']
                    iface_cfg['NETMASK' + suff] = \
                        net_prefix_to_ipv4_mask(subnet['prefix'])

                if 'gateway' in subnet and flavor != 'suse':
                    iface_cfg['DEFROUTE'] = True
                    if is_ipv6_addr(subnet['gateway']):
                        iface_cfg['IPV6_DEFAULTGW'] = subnet['gateway']
                    else:
                        iface_cfg['GATEWAY'] = subnet['gateway']

                if 'dns_search' in subnet and flavor != 'suse':
                    iface_cfg['DOMAIN'] = ' '.join(subnet['dns_search'])

                if 'dns_nameservers' in subnet and flavor != 'suse':
                    if len(subnet['dns_nameservers']) > 3:
                        # per resolv.conf(5) MAXNS sets this to 3.
                        LOG.debug("%s has %d entries in dns_nameservers. "
                                  "Only 3 are used.", iface_cfg.name,
                                  len(subnet['dns_nameservers']))
                    for i, k in enumerate(subnet['dns_nameservers'][:3], 1):
                        iface_cfg['DNS' + str(i)] = k

    @classmethod
    def _render_subnet_routes(cls, iface_cfg, route_cfg, subnets, flavor):
        # TODO(rjschwei): route configuration on SUSE distro happens via
        # ifroute-* files, see lp#1812117. SUSE currently carries a local
        # patch in their package.
        if flavor == 'suse':
            return
        for _, subnet in enumerate(subnets, start=len(iface_cfg.children)):
            subnet_type = subnet.get('type')
            for route in subnet.get('routes', []):
                is_ipv6 = subnet.get('ipv6') or is_ipv6_addr(route['gateway'])

                # Any dynamic configuration method, slaac, dhcpv6-stateful/
                # stateless should get router information from router RA's.
                if (_is_default_route(route) and subnet_type not in
                        IPV6_DYNAMIC_TYPES):
                    if (
                            (subnet.get('ipv4') and
                             route_cfg.has_set_default_ipv4) or
                            (subnet.get('ipv6') and
                             route_cfg.has_set_default_ipv6)
                    ):
                        raise ValueError("Duplicate declaration of default "
                                         "route found for interface '%s'"
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
                    if iface_cfg['BOOTPROTO'] in ('dhcp', 'dhcp4'):
                        iface_cfg['DHCLIENT_SET_DEFAULT_ROUTE'] = True
                    if 'gateway' in route:
                        if is_ipv6:
                            iface_cfg['IPV6_DEFAULTGW'] = route['gateway']
                            route_cfg.has_set_default_ipv6 = True
                        else:
                            iface_cfg['GATEWAY'] = route['gateway']
                            route_cfg.has_set_default_ipv4 = True
                    if 'metric' in route:
                        iface_cfg['METRIC'] = route['metric']

                else:
                    gw_key = 'GATEWAY%s' % route_cfg.last_idx
                    nm_key = 'NETMASK%s' % route_cfg.last_idx
                    addr_key = 'ADDRESS%s' % route_cfg.last_idx
                    metric_key = 'METRIC%s' % route_cfg.last_idx
                    route_cfg.last_idx += 1
                    # add default routes only to ifcfg files, not
                    # to route-* or route6-*
                    for (old_key, new_key) in [('gateway', gw_key),
                                               ('metric', metric_key),
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
    def _render_physical_interfaces(
            cls, network_state, iface_contents, flavor
    ):
        physical_filter = renderer.filter_by_physical
        for iface in network_state.iter_interfaces(physical_filter):
            iface_name = iface['name']
            iface_subnets = iface.get("subnets", [])
            iface_cfg = iface_contents[iface_name]
            route_cfg = iface_cfg.routes

            cls._render_subnets(
                iface_cfg, iface_subnets, network_state.has_default_route,
                flavor
            )
            cls._render_subnet_routes(
                iface_cfg, route_cfg, iface_subnets, flavor
            )

    @classmethod
    def _render_bond_interfaces(cls, network_state, iface_contents, flavor):
        bond_filter = renderer.filter_by_type('bond')
        slave_filter = renderer.filter_by_attr('bond-master')
        for iface in network_state.iter_interfaces(bond_filter):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            cls._render_bonding_opts(iface_cfg, iface)

            # Ensure that the master interface (and any of its children)
            # are actually marked as being bond types...
            master_cfgs = [iface_cfg]
            master_cfgs.extend(iface_cfg.children)
            for master_cfg in master_cfgs:
                master_cfg['BONDING_MASTER'] = True
                if flavor != 'suse':
                    master_cfg.kind = 'bond'

            if iface.get('mac_address'):
                if flavor == 'suse':
                    iface_cfg['LLADDR'] = iface.get('mac_address')
                else:
                    iface_cfg['MACADDR'] = iface.get('mac_address')

            iface_subnets = iface.get("subnets", [])
            route_cfg = iface_cfg.routes
            cls._render_subnets(
                iface_cfg, iface_subnets, network_state.has_default_route,
                flavor
            )
            cls._render_subnet_routes(
                iface_cfg, route_cfg, iface_subnets, flavor
            )

            # iter_interfaces on network-state is not sorted to produce
            # consistent numbers we need to sort.
            bond_slaves = sorted(
                [slave_iface['name'] for slave_iface in
                 network_state.iter_interfaces(slave_filter)
                 if slave_iface['bond-master'] == iface_name])

            for index, bond_slave in enumerate(bond_slaves):
                if flavor == 'suse':
                    slavestr = 'BONDING_SLAVE_%s' % index
                else:
                    slavestr = 'BONDING_SLAVE%s' % index
                iface_cfg[slavestr] = bond_slave

                slave_cfg = iface_contents[bond_slave]
                if flavor == 'suse':
                    slave_cfg['BOOTPROTO'] = 'none'
                    slave_cfg['STARTMODE'] = 'hotplug'
                else:
                    slave_cfg['MASTER'] = iface_name
                    slave_cfg['SLAVE'] = True

    @classmethod
    def _render_vlan_interfaces(cls, network_state, iface_contents, flavor):
        vlan_filter = renderer.filter_by_type('vlan')
        for iface in network_state.iter_interfaces(vlan_filter):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            if flavor == 'suse':
                vlan_id = iface.get('vlan_id')
                if vlan_id:
                    iface_cfg['VLAN_ID'] = vlan_id
                iface_cfg['ETHERDEVICE'] = iface_name[:iface_name.rfind('.')]
            else:
                iface_cfg['VLAN'] = True
                iface_cfg['PHYSDEV'] = iface_name[:iface_name.rfind('.')]

            iface_subnets = iface.get("subnets", [])
            route_cfg = iface_cfg.routes
            cls._render_subnets(
                iface_cfg, iface_subnets, network_state.has_default_route,
                flavor
            )
            cls._render_subnet_routes(
                iface_cfg, route_cfg, iface_subnets, flavor
            )

    @staticmethod
    def _render_dns(network_state, existing_dns_path=None):
        # skip writing resolv.conf if network_state doesn't include any input.
        if not any([len(network_state.dns_nameservers),
                    len(network_state.dns_searchdomains)]):
            return None
        content = resolv_conf.ResolvConf("")
        if existing_dns_path and os.path.isfile(existing_dns_path):
            content = resolv_conf.ResolvConf(util.load_file(existing_dns_path))
        for nameserver in network_state.dns_nameservers:
            content.add_nameserver(nameserver)
        for searchdomain in network_state.dns_searchdomains:
            content.add_search_domain(searchdomain)
        header = _make_header(';')
        content_str = str(content)
        if not content_str.startswith(header):
            content_str = header + '\n' + content_str
        return content_str

    @staticmethod
    def _render_networkmanager_conf(network_state, templates=None):
        content = networkmanager_conf.NetworkManagerConf("")

        # If DNS server information is provided, configure
        # NetworkManager to not manage dns, so that /etc/resolv.conf
        # does not get clobbered.
        if network_state.dns_nameservers:
            content.set_section_keypair('main', 'dns', 'none')

        if len(content) == 0:
            return None
        out = "".join([_make_header(), "\n", "\n".join(content.write()), "\n"])
        return out

    @classmethod
    def _render_bridge_interfaces(cls, network_state, iface_contents, flavor):
        bridge_key_map = {
            old_k: new_k for old_k, new_k in cls.cfg_key_maps[flavor].items()
            if old_k.startswith('bridge')}
        bridge_filter = renderer.filter_by_type('bridge')

        for iface in network_state.iter_interfaces(bridge_filter):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            if flavor != 'suse':
                iface_cfg.kind = 'bridge'
            for old_key, new_key in bridge_key_map.items():
                if old_key in iface:
                    iface_cfg[new_key] = iface[old_key]

            if flavor == 'suse':
                if 'BRIDGE_STP' in iface_cfg:
                    if iface_cfg.get('BRIDGE_STP'):
                        iface_cfg['BRIDGE_STP'] = 'on'
                    else:
                        iface_cfg['BRIDGE_STP'] = 'off'

            if iface.get('mac_address'):
                key = 'MACADDR'
                if flavor == 'suse':
                    key = 'LLADDRESS'
                iface_cfg[key] = iface.get('mac_address')

            if flavor == 'suse':
                if iface.get('bridge_ports', []):
                    iface_cfg['BRIDGE_PORTS'] = '%s' % " ".join(
                        iface.get('bridge_ports')
                    )
            # Is this the right key to get all the connected interfaces?
            for bridged_iface_name in iface.get('bridge_ports', []):
                # Ensure all bridged interfaces are correctly tagged
                # as being bridged to this interface.
                bridged_cfg = iface_contents[bridged_iface_name]
                bridged_cfgs = [bridged_cfg]
                bridged_cfgs.extend(bridged_cfg.children)
                for bridge_cfg in bridged_cfgs:
                    bridge_value = iface_name
                    if flavor == 'suse':
                        bridge_value = 'yes'
                    bridge_cfg['BRIDGE'] = bridge_value

            iface_subnets = iface.get("subnets", [])
            route_cfg = iface_cfg.routes
            cls._render_subnets(
                iface_cfg, iface_subnets, network_state.has_default_route,
                flavor
            )
            cls._render_subnet_routes(
                iface_cfg, route_cfg, iface_subnets, flavor
            )

    @classmethod
    def _render_ib_interfaces(cls, network_state, iface_contents, flavor):
        ib_filter = renderer.filter_by_type('infiniband')
        for iface in network_state.iter_interfaces(ib_filter):
            iface_name = iface['name']
            iface_cfg = iface_contents[iface_name]
            iface_cfg.kind = 'infiniband'
            iface_subnets = iface.get("subnets", [])
            route_cfg = iface_cfg.routes
            cls._render_subnets(
                iface_cfg, iface_subnets, network_state.has_default_route,
                flavor
            )
            cls._render_subnet_routes(
                iface_cfg, route_cfg, iface_subnets, flavor
            )

    @classmethod
    def _render_sysconfig(cls, base_sysconf_dir, network_state, flavor,
                          templates=None):
        '''Given state, return /etc/sysconfig files + contents'''
        if not templates:
            templates = cls.templates
        iface_contents = {}
        for iface in network_state.iter_interfaces():
            if iface['type'] == "loopback":
                continue
            iface_name = iface['name']
            iface_cfg = NetInterface(iface_name, base_sysconf_dir, templates)
            if flavor == 'suse':
                iface_cfg.drop('DEVICE')
                # If type detection fails it is considered a bug in SUSE
                iface_cfg.drop('TYPE')
            cls._render_iface_shared(iface, iface_cfg, flavor)
            iface_contents[iface_name] = iface_cfg
        cls._render_physical_interfaces(network_state, iface_contents, flavor)
        cls._render_bond_interfaces(network_state, iface_contents, flavor)
        cls._render_vlan_interfaces(network_state, iface_contents, flavor)
        cls._render_bridge_interfaces(network_state, iface_contents, flavor)
        cls._render_ib_interfaces(network_state, iface_contents, flavor)
        contents = {}
        for iface_name, iface_cfg in iface_contents.items():
            if iface_cfg or iface_cfg.children:
                contents[iface_cfg.path] = iface_cfg.to_string()
                for iface_cfg in iface_cfg.children:
                    if iface_cfg:
                        contents[iface_cfg.path] = iface_cfg.to_string()
            if iface_cfg.routes:
                for cpath, proto in zip([iface_cfg.routes.path_ipv4,
                                         iface_cfg.routes.path_ipv6],
                                        ["ipv4", "ipv6"]):
                    if cpath not in contents:
                        contents[cpath] = iface_cfg.routes.to_string(proto)
        return contents

    def render_network_state(self, network_state, templates=None, target=None):
        if not templates:
            templates = self.templates
        file_mode = 0o644
        base_sysconf_dir = util.target_path(target, self.sysconf_dir)
        for path, data in self._render_sysconfig(base_sysconf_dir,
                                                 network_state, self.flavor,
                                                 templates=templates).items():
            util.write_file(path, data, file_mode)
        if self.dns_path:
            dns_path = util.target_path(target, self.dns_path)
            resolv_content = self._render_dns(network_state,
                                              existing_dns_path=dns_path)
            if resolv_content:
                util.write_file(dns_path, resolv_content, file_mode)
        if self.networkmanager_conf_path:
            nm_conf_path = util.target_path(target,
                                            self.networkmanager_conf_path)
            nm_conf_content = self._render_networkmanager_conf(network_state,
                                                               templates)
            if nm_conf_content:
                util.write_file(nm_conf_path, nm_conf_content, file_mode)
        if self.netrules_path:
            netrules_content = self._render_persistent_net(network_state)
            netrules_path = util.target_path(target, self.netrules_path)
            util.write_file(netrules_path, netrules_content, file_mode)
        if available_nm(target=target):
            enable_ifcfg_rh(util.target_path(target, path=NM_CFG_FILE))

        sysconfig_path = util.target_path(target, templates.get('control'))
        # Distros configuring /etc/sysconfig/network as a file e.g. Centos
        if sysconfig_path.endswith('network'):
            util.ensure_dir(os.path.dirname(sysconfig_path))
            netcfg = [_make_header(), 'NETWORKING=yes']
            if network_state.use_ipv6:
                netcfg.append('NETWORKING_IPV6=yes')
                netcfg.append('IPV6_AUTOCONF=no')
            util.write_file(sysconfig_path,
                            "\n".join(netcfg) + "\n", file_mode)


def available(target=None):
    sysconfig = available_sysconfig(target=target)
    nm = available_nm(target=target)
    return (util.system_info()['variant'] in KNOWN_DISTROS
            and any([nm, sysconfig]))


def available_sysconfig(target=None):
    expected = ['ifup', 'ifdown']
    search = ['/sbin', '/usr/sbin']
    for p in expected:
        if not util.which(p, search=search, target=target):
            return False

    expected_paths = [
        'etc/sysconfig/network-scripts/network-functions',
        'etc/sysconfig/config']
    for p in expected_paths:
        if os.path.isfile(util.target_path(target, p)):
            return True
    return False


def available_nm(target=None):
    if not os.path.isfile(util.target_path(target, path=NM_CFG_FILE)):
        return False
    return True


# vi: ts=4 expandtab
