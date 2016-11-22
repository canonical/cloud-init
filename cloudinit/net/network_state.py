# Copyright (C) 2013-2014 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import functools
import logging

import six

from cloudinit import util

LOG = logging.getLogger(__name__)

NETWORK_STATE_VERSION = 1
NETWORK_STATE_REQUIRED_KEYS = {
    1: ['version', 'config', 'network_state'],
}


def parse_net_config_data(net_config, skip_broken=True):
    """Parses the config, returns NetworkState object

    :param net_config: curtin network config dict
    """
    state = None
    if 'version' in net_config and 'config' in net_config:
        nsi = NetworkStateInterpreter(version=net_config.get('version'),
                                      config=net_config.get('config'))
        nsi.parse_config(skip_broken=skip_broken)
        state = nsi.network_state
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
        }
    }

    def __init__(self, version=NETWORK_STATE_VERSION, config=None):
        self._version = version
        self._config = config
        self._network_state = copy.deepcopy(self.initial_network_state)
        self._parsed = False

    @property
    def network_state(self):
        return NetworkState(self._network_state, version=self._version)

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

    def parse_config(self, skip_broken=True):
        # rebuild network state
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
                    LOG.warn("Skipping invalid command: %s", command,
                             exc_info=True)
                    LOG.debug(self.dump_network_state())

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
        subnets = command.get('subnets')
        if subnets:
            for subnet in subnets:
                if subnet['type'] == 'static':
                    if 'netmask' in subnet and ':' in subnet['address']:
                        subnet['netmask'] = mask2cidr(subnet['netmask'])
                        for route in subnet.get('routes', []):
                            if 'netmask' in route:
                                route['netmask'] = mask2cidr(route['netmask'])
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

    @ensure_command_keys(['name', 'bridge_interfaces', 'params'])
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
        for param, val in command.get('params').items():
            iface.update({param: val})

        interfaces.update({iface['name']: iface})

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
        routes = self._network_state.get('routes', [])
        network, cidr = command['destination'].split("/")
        netmask = cidr2mask(int(cidr))
        route = {
            'network': network,
            'netmask': netmask,
            'gateway': command.get('gateway'),
            'metric': command.get('metric'),
        }
        routes.append(route)


def cidr2mask(cidr):
    mask = [0, 0, 0, 0]
    for i in list(range(0, cidr)):
        idx = int(i / 8)
        mask[idx] = mask[idx] + (1 << (7 - i % 8))
    return ".".join([str(x) for x in mask])


def ipv4mask2cidr(mask):
    if '.' not in mask:
        return mask
    return sum([bin(int(x)).count('1') for x in mask.split('.')])


def ipv6mask2cidr(mask):
    if ':' not in mask:
        return mask

    bitCount = [0, 0x8000, 0xc000, 0xe000, 0xf000, 0xf800, 0xfc00, 0xfe00,
                0xff00, 0xff80, 0xffc0, 0xffe0, 0xfff0, 0xfff8, 0xfffc,
                0xfffe, 0xffff]
    cidr = 0
    for word in mask.split(':'):
        if not word or int(word, 16) == 0:
            break
        cidr += bitCount.index(int(word, 16))

    return cidr


def mask2cidr(mask):
    if ':' in mask:
        return ipv6mask2cidr(mask)
    elif '.' in mask:
        return ipv4mask2cidr(mask)
    else:
        return mask

# vi: ts=4 expandtab
