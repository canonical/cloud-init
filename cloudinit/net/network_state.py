# Copyright (C) 2017 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import functools
import logging
import socket
import struct

import six

from cloudinit import util

LOG = logging.getLogger(__name__)

NETWORK_STATE_VERSION = 1
NETWORK_STATE_REQUIRED_KEYS = {
    1: ['version', 'config', 'network_state'],
}
NETWORK_V2_KEY_FILTER = [
    'addresses', 'dhcp4', 'dhcp6', 'gateway4', 'gateway6', 'interfaces',
    'match', 'mtu', 'nameservers', 'renderer', 'set-name', 'wakeonlan'
]

NET_CONFIG_TO_V2 = {
    'bond': {'bond-ad-select': 'ad-select',
             'bond-arp-interval': 'arp-interval',
             'bond-arp-ip-target': 'arp-ip-target',
             'bond-arp-validate': 'arp-validate',
             'bond-downdelay': 'down-delay',
             'bond-fail-over-mac': 'fail-over-mac-policy',
             'bond-lacp-rate': 'lacp-rate',
             'bond-miimon': 'mii-monitor-interval',
             'bond-min-links': 'min-links',
             'bond-mode': 'mode',
             'bond-num-grat-arp': 'gratuitious-arp',
             'bond-primary': 'primary',
             'bond-primary-reselect': 'primary-reselect-policy',
             'bond-updelay': 'up-delay',
             'bond-xmit-hash-policy': 'transmit-hash-policy'},
    'bridge': {'bridge_ageing': 'ageing-time',
               'bridge_bridgeprio': 'priority',
               'bridge_fd': 'forward-delay',
               'bridge_gcint': None,
               'bridge_hello': 'hello-time',
               'bridge_maxage': 'max-age',
               'bridge_maxwait': None,
               'bridge_pathcost': 'path-cost',
               'bridge_portprio': 'port-priority',
               'bridge_stp': 'stp',
               'bridge_waitport': None}}


def parse_net_config_data(net_config, skip_broken=True):
    """Parses the config, returns NetworkState object

    :param net_config: curtin network config dict
    """
    state = None
    version = net_config.get('version')
    config = net_config.get('config')
    if version == 2:
        # v2 does not have explicit 'config' key so we
        # pass the whole net-config as-is
        config = net_config

    if version and config:
        nsi = NetworkStateInterpreter(version=version, config=config)
        nsi.parse_config(skip_broken=skip_broken)
        state = nsi.get_network_state()

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


def from_state_file(state_file):
    state = util.read_conf(state_file)
    nsi = NetworkStateInterpreter()
    nsi.load(state)
    return nsi


def diff_keys(expected, actual):
    missing = set(expected)
    for key in actual:
        missing.discard(key)
    return missing


class InvalidCommand(Exception):
    pass


def ensure_command_keys(required_keys):

    def wrapper(func):

        @functools.wraps(func)
        def decorator(self, command, *args, **kwargs):
            if required_keys:
                missing_keys = diff_keys(required_keys, command)
                if missing_keys:
                    raise InvalidCommand("Command missing %s of required"
                                         " keys %s" % (missing_keys,
                                                       required_keys))
            return func(self, command, *args, **kwargs)

        return decorator

    return wrapper


class CommandHandlerMeta(type):
    """Metaclass that dynamically creates a 'command_handlers' attribute.

    This will scan the to-be-created class for methods that start with
    'handle_' and on finding those will populate a class attribute mapping
    so that those methods can be quickly located and called.
    """
    def __new__(cls, name, parents, dct):
        command_handlers = {}
        for attr_name, attr in dct.items():
            if callable(attr) and attr_name.startswith('handle_'):
                handles_what = attr_name[len('handle_'):]
                if handles_what:
                    command_handlers[handles_what] = attr
        dct['command_handlers'] = command_handlers
        return super(CommandHandlerMeta, cls).__new__(cls, name,
                                                      parents, dct)


class NetworkState(object):

    def __init__(self, network_state, version=NETWORK_STATE_VERSION):
        self._network_state = copy.deepcopy(network_state)
        self._version = version
        self.use_ipv6 = network_state.get('use_ipv6', False)

    @property
    def config(self):
        return self._network_state['config']

    @property
    def version(self):
        return self._version

    def iter_routes(self, filter_func=None):
        for route in self._network_state.get('routes', []):
            if filter_func is not None:
                if filter_func(route):
                    yield route
            else:
                yield route

    @property
    def dns_nameservers(self):
        try:
            return self._network_state['dns']['nameservers']
        except KeyError:
            return []

    @property
    def dns_searchdomains(self):
        try:
            return self._network_state['dns']['search']
        except KeyError:
            return []

    def iter_interfaces(self, filter_func=None):
        ifaces = self._network_state.get('interfaces', {})
        for iface in six.itervalues(ifaces):
            if filter_func is None:
                yield iface
            else:
                if filter_func(iface):
                    yield iface


@six.add_metaclass(CommandHandlerMeta)
class NetworkStateInterpreter(object):

    initial_network_state = {
        'interfaces': {},
        'routes': [],
        'dns': {
            'nameservers': [],
            'search': [],
        },
        'use_ipv6': False,
        'config': None,
    }

    def __init__(self, version=NETWORK_STATE_VERSION, config=None):
        self._version = version
        self._config = config
        self._network_state = copy.deepcopy(self.initial_network_state)
        self._network_state['config'] = config
        self._parsed = False

    @property
    def network_state(self):
        return NetworkState(self._network_state, version=self._version)

    @property
    def use_ipv6(self):
        return self._network_state.get('use_ipv6')

    @use_ipv6.setter
    def use_ipv6(self, val):
        self._network_state.update({'use_ipv6': val})

    def dump(self):
        state = {
            'version': self._version,
            'config': self._config,
            'network_state': self._network_state,
        }
        return util.yaml_dumps(state)

    def load(self, state):
        if 'version' not in state:
            LOG.error('Invalid state, missing version field')
            raise ValueError('Invalid state, missing version field')

        required_keys = NETWORK_STATE_REQUIRED_KEYS[state['version']]
        missing_keys = diff_keys(required_keys, state)
        if missing_keys:
            msg = 'Invalid state, missing keys: %s' % (missing_keys)
            LOG.error(msg)
            raise ValueError(msg)

        # v1 - direct attr mapping, except version
        for key in [k for k in required_keys if k not in ['version']]:
            setattr(self, key, state[key])

    def dump_network_state(self):
        return util.yaml_dumps(self._network_state)

    def as_dict(self):
        return {'version': self._version, 'config': self._config}

    def get_network_state(self):
        ns = self.network_state
        return ns

    def parse_config(self, skip_broken=True):
        if self._version == 1:
            self.parse_config_v1(skip_broken=skip_broken)
            self._parsed = True
        elif self._version == 2:
            self.parse_config_v2(skip_broken=skip_broken)
            self._parsed = True

    def parse_config_v1(self, skip_broken=True):
        for command in self._config:
            command_type = command['type']
            try:
                handler = self.command_handlers[command_type]
            except KeyError:
                raise RuntimeError("No handler found for"
                                   " command '%s'" % command_type)
            try:
                handler(self, command)
            except InvalidCommand:
                if not skip_broken:
                    raise
                else:
                    LOG.warning("Skipping invalid command: %s", command,
                                exc_info=True)
                    LOG.debug(self.dump_network_state())

    def parse_config_v2(self, skip_broken=True):
        for command_type, command in self._config.items():
            if command_type == 'version':
                continue
            try:
                handler = self.command_handlers[command_type]
            except KeyError:
                raise RuntimeError("No handler found for"
                                   " command '%s'" % command_type)
            try:
                handler(self, command)
                self._v2_common(command)
            except InvalidCommand:
                if not skip_broken:
                    raise
                else:
                    LOG.warning("Skipping invalid command: %s", command,
                                exc_info=True)
                    LOG.debug(self.dump_network_state())

    @ensure_command_keys(['name'])
    def handle_loopback(self, command):
        return self.handle_physical(command)

    @ensure_command_keys(['name'])
    def handle_physical(self, command):
        '''
        command = {
            'type': 'physical',
            'mac_address': 'c0:d6:9f:2c:e8:80',
            'name': 'eth0',
            'subnets': [
                {'type': 'dhcp4'}
             ]
        }
        '''

        interfaces = self._network_state.get('interfaces', {})
        iface = interfaces.get(command['name'], {})
        for param, val in command.get('params', {}).items():
            iface.update({param: val})

        # convert subnet ipv6 netmask to cidr as needed
        subnets = _normalize_subnets(command.get('subnets'))

        # automatically set 'use_ipv6' if any addresses are ipv6
        if not self.use_ipv6:
            for subnet in subnets:
                if (subnet.get('type').endswith('6') or
                        is_ipv6_addr(subnet.get('address'))):
                    self.use_ipv6 = True
                    break

        iface.update({
            'name': command.get('name'),
            'type': command.get('type'),
            'mac_address': command.get('mac_address'),
            'inet': 'inet',
            'mode': 'manual',
            'mtu': command.get('mtu'),
            'address': None,
            'gateway': None,
            'subnets': subnets,
        })
        self._network_state['interfaces'].update({command.get('name'): iface})
        self.dump_network_state()

    @ensure_command_keys(['name', 'vlan_id', 'vlan_link'])
    def handle_vlan(self, command):
        '''
            auto eth0.222
            iface eth0.222 inet static
                    address 10.10.10.1
                    netmask 255.255.255.0
                    hwaddress ether BC:76:4E:06:96:B3
                    vlan-raw-device eth0
        '''
        interfaces = self._network_state.get('interfaces', {})
        self.handle_physical(command)
        iface = interfaces.get(command.get('name'), {})
        iface['vlan-raw-device'] = command.get('vlan_link')
        iface['vlan_id'] = command.get('vlan_id')
        interfaces.update({iface['name']: iface})

    @ensure_command_keys(['name', 'bond_interfaces', 'params'])
    def handle_bond(self, command):
        '''
    #/etc/network/interfaces
    auto eth0
    iface eth0 inet manual
        bond-master bond0
        bond-mode 802.3ad

    auto eth1
    iface eth1 inet manual
        bond-master bond0
        bond-mode 802.3ad

    auto bond0
    iface bond0 inet static
         address 192.168.0.10
         gateway 192.168.0.1
         netmask 255.255.255.0
         bond-slaves none
         bond-mode 802.3ad
         bond-miimon 100
         bond-downdelay 200
         bond-updelay 200
         bond-lacp-rate 4
        '''

        self.handle_physical(command)
        interfaces = self._network_state.get('interfaces')
        iface = interfaces.get(command.get('name'), {})
        for param, val in command.get('params').items():
            iface.update({param: val})
        iface.update({'bond-slaves': 'none'})
        self._network_state['interfaces'].update({iface['name']: iface})

        # handle bond slaves
        for ifname in command.get('bond_interfaces'):
            if ifname not in interfaces:
                cmd = {
                    'name': ifname,
                    'type': 'bond',
                }
                # inject placeholder
                self.handle_physical(cmd)

            interfaces = self._network_state.get('interfaces', {})
            bond_if = interfaces.get(ifname)
            bond_if['bond-master'] = command.get('name')
            # copy in bond config into slave
            for param, val in command.get('params').items():
                bond_if.update({param: val})
            self._network_state['interfaces'].update({ifname: bond_if})

    @ensure_command_keys(['name', 'bridge_interfaces'])
    def handle_bridge(self, command):
        '''
            auto br0
            iface br0 inet static
                    address 10.10.10.1
                    netmask 255.255.255.0
                    bridge_ports eth0 eth1
                    bridge_stp off
                    bridge_fd 0
                    bridge_maxwait 0

        bridge_params = [
            "bridge_ports",
            "bridge_ageing",
            "bridge_bridgeprio",
            "bridge_fd",
            "bridge_gcint",
            "bridge_hello",
            "bridge_hw",
            "bridge_maxage",
            "bridge_maxwait",
            "bridge_pathcost",
            "bridge_portprio",
            "bridge_stp",
            "bridge_waitport",
        ]
        '''

        # find one of the bridge port ifaces to get mac_addr
        # handle bridge_slaves
        interfaces = self._network_state.get('interfaces', {})
        for ifname in command.get('bridge_interfaces'):
            if ifname in interfaces:
                continue

            cmd = {
                'name': ifname,
            }
            # inject placeholder
            self.handle_physical(cmd)

        interfaces = self._network_state.get('interfaces', {})
        self.handle_physical(command)
        iface = interfaces.get(command.get('name'), {})
        iface['bridge_ports'] = command['bridge_interfaces']
        for param, val in command.get('params', {}).items():
            iface.update({param: val})

        # convert value to boolean
        bridge_stp = iface.get('bridge_stp')
        if bridge_stp is not None and type(bridge_stp) != bool:
            if bridge_stp in ['on', '1', 1]:
                bridge_stp = True
            elif bridge_stp in ['off', '0', 0]:
                bridge_stp = False
            else:
                raise ValueError(
                    'Cannot convert bridge_stp value ({stp}) to'
                    ' boolean'.format(stp=bridge_stp))
            iface.update({'bridge_stp': bridge_stp})

        interfaces.update({iface['name']: iface})

    @ensure_command_keys(['name'])
    def handle_infiniband(self, command):
        self.handle_physical(command)

    @ensure_command_keys(['address'])
    def handle_nameserver(self, command):
        dns = self._network_state.get('dns')
        if 'address' in command:
            addrs = command['address']
            if not type(addrs) == list:
                addrs = [addrs]
            for addr in addrs:
                dns['nameservers'].append(addr)
        if 'search' in command:
            paths = command['search']
            if not isinstance(paths, list):
                paths = [paths]
            for path in paths:
                dns['search'].append(path)

    @ensure_command_keys(['destination'])
    def handle_route(self, command):
        self._network_state['routes'].append(_normalize_route(command))

    # V2 handlers
    def handle_bonds(self, command):
        '''
        v2_command = {
          bond0: {
            'interfaces': ['interface0', 'interface1'],
            'parameters': {
               'mii-monitor-interval': 100,
               'mode': '802.3ad',
               'xmit_hash_policy': 'layer3+4'}},
          bond1: {
            'bond-slaves': ['interface2', 'interface7'],
            'parameters': {
                'mode': 1,
            }
          }
        }

        v1_command = {
            'type': 'bond'
            'name': 'bond0',
            'bond_interfaces': [interface0, interface1],
            'params': {
                'bond-mode': '802.3ad',
                'bond_miimon: 100,
                'bond_xmit_hash_policy': 'layer3+4',
            }
        }

        '''
        self._handle_bond_bridge(command, cmd_type='bond')

    def handle_bridges(self, command):

        '''
        v2_command = {
          br0: {
            'interfaces': ['interface0', 'interface1'],
            'forward-delay': 0,
            'stp': False,
            'maxwait': 0,
          }
        }

        v1_command = {
            'type': 'bridge'
            'name': 'br0',
            'bridge_interfaces': [interface0, interface1],
            'params': {
                'bridge_stp': 'off',
                'bridge_fd: 0,
                'bridge_maxwait': 0
            }
        }

        '''
        self._handle_bond_bridge(command, cmd_type='bridge')

    def handle_ethernets(self, command):
        '''
        ethernets:
          eno1:
            match:
              macaddress: 00:11:22:33:44:55
            wakeonlan: true
            dhcp4: true
            dhcp6: false
            addresses:
              - 192.168.14.2/24
              - 2001:1::1/64
            gateway4: 192.168.14.1
            gateway6: 2001:1::2
            nameservers:
              search: [foo.local, bar.local]
              addresses: [8.8.8.8, 8.8.4.4]
          lom:
            match:
              driver: ixgbe
            set-name: lom1
            dhcp6: true
          switchports:
            match:
              name: enp2*
            mtu: 1280

        command = {
            'type': 'physical',
            'mac_address': 'c0:d6:9f:2c:e8:80',
            'name': 'eth0',
            'subnets': [
                {'type': 'dhcp4'}
             ]
        }
        '''
        for eth, cfg in command.items():
            phy_cmd = {
                'type': 'physical',
                'name': cfg.get('set-name', eth),
            }
            mac_address = cfg.get('match', {}).get('macaddress', None)
            if not mac_address:
                LOG.debug('NetworkState Version2: missing "macaddress" info '
                          'in config entry: %s: %s', eth, str(cfg))
            phy_cmd.update({'mac_address': mac_address})

            for key in ['mtu', 'match', 'wakeonlan']:
                if key in cfg:
                    phy_cmd.update({key: cfg.get(key)})

            subnets = self._v2_to_v1_ipcfg(cfg)
            if len(subnets) > 0:
                phy_cmd.update({'subnets': subnets})

            LOG.debug('v2(ethernets) -> v1(physical):\n%s', phy_cmd)
            self.handle_physical(phy_cmd)

    def handle_vlans(self, command):
        '''
        v2_vlans = {
            'eth0.123': {
                'id': 123,
                'link': 'eth0',
                'dhcp4': True,
            }
        }

        v1_command = {
            'type': 'vlan',
            'name': 'eth0.123',
            'vlan_link': 'eth0',
            'vlan_id': 123,
            'subnets': [{'type': 'dhcp4'}],
        }
        '''
        for vlan, cfg in command.items():
            vlan_cmd = {
                'type': 'vlan',
                'name': vlan,
                'vlan_id': cfg.get('id'),
                'vlan_link': cfg.get('link'),
            }
            subnets = self._v2_to_v1_ipcfg(cfg)
            if len(subnets) > 0:
                vlan_cmd.update({'subnets': subnets})
            LOG.debug('v2(vlans) -> v1(vlan):\n%s', vlan_cmd)
            self.handle_vlan(vlan_cmd)

    def handle_wifis(self, command):
        LOG.warning('Wifi configuration is only available to distros with'
                    'netplan rendering support.')

    def _v2_common(self, cfg):
        LOG.debug('v2_common: handling config:\n%s', cfg)
        if 'nameservers' in cfg:
            search = cfg.get('nameservers').get('search', [])
            dns = cfg.get('nameservers').get('addresses', [])
            name_cmd = {'type': 'nameserver'}
            if len(search) > 0:
                name_cmd.update({'search': search})
            if len(dns) > 0:
                name_cmd.update({'addresses': dns})
            LOG.debug('v2(nameserver) -> v1(nameserver):\n%s', name_cmd)
            self.handle_nameserver(name_cmd)

    def _handle_bond_bridge(self, command, cmd_type=None):
        """Common handler for bond and bridge types"""

        # inverse mapping for v2 keynames to v1 keynames
        v2key_to_v1 = dict((v, k) for k, v in
                           NET_CONFIG_TO_V2.get(cmd_type).items())

        for item_name, item_cfg in command.items():
            item_params = dict((key, value) for (key, value) in
                               item_cfg.items() if key not in
                               NETWORK_V2_KEY_FILTER)
            v1_cmd = {
                'type': cmd_type,
                'name': item_name,
                cmd_type + '_interfaces': item_cfg.get('interfaces'),
                'params': dict((v2key_to_v1[k], v) for k, v in
                               item_params.get('parameters', {}).items())
            }
            subnets = self._v2_to_v1_ipcfg(item_cfg)
            if len(subnets) > 0:
                v1_cmd.update({'subnets': subnets})

            LOG.debug('v2(%s) -> v1(%s):\n%s', cmd_type, cmd_type, v1_cmd)
            if cmd_type == "bridge":
                self.handle_bridge(v1_cmd)
            elif cmd_type == "bond":
                self.handle_bond(v1_cmd)
            else:
                raise ValueError('Unknown command type: {cmd_type}'.format(
                    cmd_type=cmd_type))

    def _v2_to_v1_ipcfg(self, cfg):
        """Common ipconfig extraction from v2 to v1 subnets array."""

        subnets = []
        if 'dhcp4' in cfg:
            subnets.append({'type': 'dhcp4'})
        if 'dhcp6' in cfg:
            self.use_ipv6 = True
            subnets.append({'type': 'dhcp6'})

        gateway4 = None
        gateway6 = None
        nameservers = {}
        for address in cfg.get('addresses', []):
            subnet = {
                'type': 'static',
                'address': address,
            }

            if ":" in address:
                if 'gateway6' in cfg and gateway6 is None:
                    gateway6 = cfg.get('gateway6')
                    subnet.update({'gateway': gateway6})
            else:
                if 'gateway4' in cfg and gateway4 is None:
                    gateway4 = cfg.get('gateway4')
                    subnet.update({'gateway': gateway4})

            if 'nameservers' in cfg and not nameservers:
                addresses = cfg.get('nameservers').get('addresses')
                if addresses:
                    nameservers['dns_nameservers'] = addresses
                search = cfg.get('nameservers').get('search')
                if search:
                    nameservers['dns_search'] = search
                subnet.update(nameservers)

            subnets.append(subnet)

        routes = []
        for route in cfg.get('routes', []):
            routes.append(_normalize_route(
                {'destination': route.get('to'), 'gateway': route.get('via')}))

        # v2 routes are bound to the interface, in v1 we add them under
        # the first subnet since there isn't an equivalent interface level.
        if len(subnets) and len(routes):
            subnets[0]['routes'] = routes

        return subnets


def _normalize_subnet(subnet):
    # Prune all keys with None values.
    subnet = copy.deepcopy(subnet)
    normal_subnet = dict((k, v) for k, v in subnet.items() if v)

    if subnet.get('type') in ('static', 'static6'):
        normal_subnet.update(
            _normalize_net_keys(normal_subnet, address_keys=('address',)))
    normal_subnet['routes'] = [_normalize_route(r)
                               for r in subnet.get('routes', [])]

    def listify(snet, name):
        if name in snet and not isinstance(snet[name], list):
            snet[name] = snet[name].split()

    for k in ('dns_search', 'dns_nameservers'):
        listify(normal_subnet, k)

    return normal_subnet


def _normalize_net_keys(network, address_keys=()):
    """Normalize dictionary network keys returning prefix and address keys.

    @param network: A dict of network-related definition containing prefix,
        netmask and address_keys.
    @param address_keys: A tuple of keys to search for representing the address
        or cidr. The first address_key discovered will be used for
        normalization.

    @returns: A dict containing normalized prefix and matching addr_key.
    """
    net = dict((k, v) for k, v in network.items() if v)
    addr_key = None
    for key in address_keys:
        if net.get(key):
            addr_key = key
            break
    if not addr_key:
        message = (
            'No config network address keys [%s] found in %s' %
            (','.join(address_keys), network))
        LOG.error(message)
        raise ValueError(message)

    addr = net.get(addr_key)
    ipv6 = is_ipv6_addr(addr)
    netmask = net.get('netmask')
    if "/" in addr:
        addr_part, _, maybe_prefix = addr.partition("/")
        net[addr_key] = addr_part
        try:
            prefix = int(maybe_prefix)
        except ValueError:
            # this supports input of <address>/255.255.255.0
            prefix = mask_to_net_prefix(maybe_prefix)
    elif netmask:
        prefix = mask_to_net_prefix(netmask)
    elif 'prefix' in net:
        prefix = int(net['prefix'])
    else:
        prefix = 64 if ipv6 else 24

    if 'prefix' in net and str(net['prefix']) != str(prefix):
        LOG.warning("Overwriting existing 'prefix' with '%s' in "
                    "network info: %s", prefix, net)
    net['prefix'] = prefix

    if ipv6:
        # TODO: we could/maybe should add this back with the very uncommon
        # 'netmask' for ipv6.  We need a 'net_prefix_to_ipv6_mask' for that.
        if 'netmask' in net:
            del net['netmask']
    else:
        net['netmask'] = net_prefix_to_ipv4_mask(net['prefix'])

    return net


def _normalize_route(route):
    """normalize a route.
    return a dictionary with only:
       'type': 'route' (only present if it was present in input)
       'network': the network portion of the route as a string.
       'prefix': the network prefix for address as an integer.
       'metric': integer metric (only if present in input).
       'netmask': netmask (string) equivalent to prefix iff network is ipv4.
       """
    # Prune None-value keys.  Specifically allow 0 (a valid metric).
    normal_route = dict((k, v) for k, v in route.items()
                        if v not in ("", None))
    if 'destination' in normal_route:
        normal_route['network'] = normal_route['destination']
        del normal_route['destination']

    normal_route.update(
        _normalize_net_keys(
            normal_route, address_keys=('network', 'destination')))

    metric = normal_route.get('metric')
    if metric:
        try:
            normal_route['metric'] = int(metric)
        except ValueError:
            raise TypeError(
                'Route config metric {} is not an integer'.format(metric))
    return normal_route


def _normalize_subnets(subnets):
    if not subnets:
        subnets = []
    return [_normalize_subnet(s) for s in subnets]


def is_ipv6_addr(address):
    if not address:
        return False
    return ":" in str(address)


def subnet_is_ipv6(subnet):
    """Common helper for checking network_state subnets for ipv6."""
    # 'static6' or 'dhcp6'
    if subnet['type'].endswith('6'):
        # This is a request for DHCPv6.
        return True
    elif subnet['type'] == 'static' and is_ipv6_addr(subnet.get('address')):
        return True
    return False


def net_prefix_to_ipv4_mask(prefix):
    """Convert a network prefix to an ipv4 netmask.

    This is the inverse of ipv4_mask_to_net_prefix.
        24 -> "255.255.255.0"
    Also supports input as a string."""
    mask = socket.inet_ntoa(
        struct.pack(">I", (0xffffffff << (32 - int(prefix)) & 0xffffffff)))
    return mask


def ipv4_mask_to_net_prefix(mask):
    """Convert an ipv4 netmask into a network prefix length.

    If the input is already an integer or a string representation of
    an integer, then int(mask) will be returned.
       "255.255.255.0" => 24
       str(24)         => 24
       "24"            => 24
    """
    if isinstance(mask, int):
        return mask
    if isinstance(mask, six.string_types):
        try:
            return int(mask)
        except ValueError:
            pass
    else:
        raise TypeError("mask '%s' is not a string or int")

    if '.' not in mask:
        raise ValueError("netmask '%s' does not contain a '.'" % mask)

    toks = mask.split(".")
    if len(toks) != 4:
        raise ValueError("netmask '%s' had only %d parts" % (mask, len(toks)))

    return sum([bin(int(x)).count('1') for x in toks])


def ipv6_mask_to_net_prefix(mask):
    """Convert an ipv6 netmask (very uncommon) or prefix (64) to prefix.

    If 'mask' is an integer or string representation of one then
    int(mask) will be returned.
    """

    if isinstance(mask, int):
        return mask
    if isinstance(mask, six.string_types):
        try:
            return int(mask)
        except ValueError:
            pass
    else:
        raise TypeError("mask '%s' is not a string or int")

    if ':' not in mask:
        raise ValueError("mask '%s' does not have a ':'")

    bitCount = [0, 0x8000, 0xc000, 0xe000, 0xf000, 0xf800, 0xfc00, 0xfe00,
                0xff00, 0xff80, 0xffc0, 0xffe0, 0xfff0, 0xfff8, 0xfffc,
                0xfffe, 0xffff]
    prefix = 0
    for word in mask.split(':'):
        if not word or int(word, 16) == 0:
            break
        prefix += bitCount.index(int(word, 16))

    return prefix


def mask_to_net_prefix(mask):
    """Return the network prefix for the netmask provided.

    Supports ipv4 or ipv6 netmasks."""
    try:
        # if 'mask' is a prefix that is an integer.
        # then just return it.
        return int(mask)
    except ValueError:
        pass
    if is_ipv6_addr(mask):
        return ipv6_mask_to_net_prefix(mask)
    else:
        return ipv4_mask_to_net_prefix(mask)


def mask_and_ipv4_to_bcast_addr(mask, ip):
    """Calculate the broadcast address from the subnet mask and ip addr.

    Supports ipv4 only."""
    ip_bin = int(''.join([bin(int(x) + 256)[3:] for x in ip.split('.')]), 2)
    mask_dec = ipv4_mask_to_net_prefix(mask)
    bcast_bin = ip_bin | (2**(32 - mask_dec) - 1)
    bcast_str = '.'.join([str(bcast_bin >> (i << 3) & 0xFF)
                          for i in range(4)[::-1]])
    return bcast_str


# vi: ts=4 expandtab
