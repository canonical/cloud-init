#   Copyright (C) 2013-2014 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
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

from curtin.log import LOG
import curtin.config as curtin_config

NETWORK_STATE_VERSION = 1
NETWORK_STATE_REQUIRED_KEYS = {
    1: ['version', 'config', 'network_state'],
}


def from_state_file(state_file):
    network_state = None
    state = curtin_config.load_config(state_file)
    network_state = NetworkState()
    network_state.load(state)

    return network_state


class NetworkState:
    def __init__(self, version=NETWORK_STATE_VERSION, config=None):
        self.version = version
        self.config = config
        self.network_state = {
            'interfaces': {},
            'routes': [],
            'dns': {
                'nameservers': [],
                'search': [],
            }
        }
        self.command_handlers = self.get_command_handlers()

    def get_command_handlers(self):
        METHOD_PREFIX = 'handle_'
        methods = filter(lambda x: callable(getattr(self, x)) and
                         x.startswith(METHOD_PREFIX),  dir(self))
        handlers = {}
        for m in methods:
            key = m.replace(METHOD_PREFIX, '')
            handlers[key] = getattr(self, m)

        return handlers

    def dump(self):
        state = {
            'version': self.version,
            'config': self.config,
            'network_state': self.network_state,
        }
        return curtin_config.dump_config(state)

    def load(self, state):
        if 'version' not in state:
            LOG.error('Invalid state, missing version field')
            raise Exception('Invalid state, missing version field')

        required_keys = NETWORK_STATE_REQUIRED_KEYS[state['version']]
        if not self.valid_command(state, required_keys):
            msg = 'Invalid state, missing keys: {}'.format(required_keys)
            LOG.error(msg)
            raise Exception(msg)

        # v1 - direct attr mapping, except version
        for key in [k for k in required_keys if k not in ['version']]:
            setattr(self, key, state[key])
        self.command_handlers = self.get_command_handlers()

    def dump_network_state(self):
        return curtin_config.dump_config(self.network_state)

    def parse_config(self):
        # rebuild network state
        for command in self.config:
            handler = self.command_handlers.get(command['type'])
            handler(command)

    def valid_command(self, command, required_keys):
        if not required_keys:
            return False

        found_keys = [key for key in command.keys() if key in required_keys]
        return len(found_keys) == len(required_keys)

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
        required_keys = [
            'name',
        ]
        if not self.valid_command(command, required_keys):
            LOG.warn('Skipping Invalid command: {}'.format(command))
            LOG.debug(self.dump_network_state())
            return

        interfaces = self.network_state.get('interfaces')
        iface = interfaces.get(command['name'], {})
        for param, val in command.get('params', {}).items():
            iface.update({param: val})
        iface.update({
            'name': command.get('name'),
            'type': command.get('type'),
            'mac_address': command.get('mac_address'),
            'inet': 'inet',
            'mode': 'manual',
            'mtu': command.get('mtu'),
            'address': None,
            'gateway': None,
            'subnets': command.get('subnets'),
        })
        self.network_state['interfaces'].update({command.get('name'): iface})
        self.dump_network_state()

    def handle_vlan(self, command):
        '''
            auto eth0.222
            iface eth0.222 inet static
                    address 10.10.10.1
                    netmask 255.255.255.0
                    vlan-raw-device eth0
        '''
        required_keys = [
            'name',
            'vlan_link',
            'vlan_id',
        ]
        if not self.valid_command(command, required_keys):
            print('Skipping Invalid command: {}'.format(command))
            print(self.dump_network_state())
            return

        interfaces = self.network_state.get('interfaces')
        self.handle_physical(command)
        iface = interfaces.get(command.get('name'), {})
        iface['vlan-raw-device'] = command.get('vlan_link')
        iface['vlan_id'] = command.get('vlan_id')
        interfaces.update({iface['name']: iface})

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
        required_keys = [
            'name',
            'bond_interfaces',
            'params',
        ]
        if not self.valid_command(command, required_keys):
            print('Skipping Invalid command: {}'.format(command))
            print(self.dump_network_state())
            return

        self.handle_physical(command)
        interfaces = self.network_state.get('interfaces')
        iface = interfaces.get(command.get('name'), {})
        for param, val in command.get('params').items():
            iface.update({param: val})
        iface.update({'bond-slaves': 'none'})
        self.network_state['interfaces'].update({iface['name']: iface})

        # handle bond slaves
        for ifname in command.get('bond_interfaces'):
            if ifname not in interfaces:
                cmd = {
                    'name': ifname,
                    'type': 'bond',
                }
                # inject placeholder
                self.handle_physical(cmd)

            interfaces = self.network_state.get('interfaces')
            bond_if = interfaces.get(ifname)
            bond_if['bond-master'] = command.get('name')
            # copy in bond config into slave
            for param, val in command.get('params').items():
                bond_if.update({param: val})
            self.network_state['interfaces'].update({ifname: bond_if})

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
        required_keys = [
            'name',
            'bridge_interfaces',
            'params',
        ]
        if not self.valid_command(command, required_keys):
            print('Skipping Invalid command: {}'.format(command))
            print(self.dump_network_state())
            return

        # find one of the bridge port ifaces to get mac_addr
        # handle bridge_slaves
        interfaces = self.network_state.get('interfaces')
        for ifname in command.get('bridge_interfaces'):
            if ifname in interfaces:
                continue

            cmd = {
                'name': ifname,
            }
            # inject placeholder
            self.handle_physical(cmd)

        interfaces = self.network_state.get('interfaces')
        self.handle_physical(command)
        iface = interfaces.get(command.get('name'), {})
        iface['bridge_ports'] = command['bridge_interfaces']
        for param, val in command.get('params').items():
            iface.update({param: val})

        interfaces.update({iface['name']: iface})

    def handle_nameserver(self, command):
        required_keys = [
            'address',
        ]
        if not self.valid_command(command, required_keys):
            print('Skipping Invalid command: {}'.format(command))
            print(self.dump_network_state())
            return

        dns = self.network_state.get('dns')
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

    def handle_route(self, command):
        required_keys = [
            'destination',
        ]
        if not self.valid_command(command, required_keys):
            print('Skipping Invalid command: {}'.format(command))
            print(self.dump_network_state())
            return

        routes = self.network_state.get('routes')
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


if __name__ == '__main__':
    import sys
    import random
    from curtin import net

    def load_config(nc):
        version = nc.get('version')
        config = nc.get('config')
        return (version, config)

    def test_parse(network_config):
        (version, config) = load_config(network_config)
        ns1 = NetworkState(version=version, config=config)
        ns1.parse_config()
        random.shuffle(config)
        ns2 = NetworkState(version=version, config=config)
        ns2.parse_config()
        print("----NS1-----")
        print(ns1.dump_network_state())
        print()
        print("----NS2-----")
        print(ns2.dump_network_state())
        print("NS1 == NS2 ?=> {}".format(
            ns1.network_state == ns2.network_state))
        eni = net.render_interfaces(ns2.network_state)
        print(eni)
        udev_rules = net.render_persistent_net(ns2.network_state)
        print(udev_rules)

    def test_dump_and_load(network_config):
        print("Loading network_config into NetworkState")
        (version, config) = load_config(network_config)
        ns1 = NetworkState(version=version, config=config)
        ns1.parse_config()
        print("Dumping state to file")
        ns1_dump = ns1.dump()
        ns1_state = "/tmp/ns1.state"
        with open(ns1_state, "w+") as f:
            f.write(ns1_dump)

        print("Loading state from file")
        ns2 = from_state_file(ns1_state)
        print("NS1 == NS2 ?=> {}".format(
            ns1.network_state == ns2.network_state))

    def test_output(network_config):
        (version, config) = load_config(network_config)
        ns1 = NetworkState(version=version, config=config)
        ns1.parse_config()
        random.shuffle(config)
        ns2 = NetworkState(version=version, config=config)
        ns2.parse_config()
        print("NS1 == NS2 ?=> {}".format(
            ns1.network_state == ns2.network_state))
        eni_1 = net.render_interfaces(ns1.network_state)
        eni_2 = net.render_interfaces(ns2.network_state)
        print(eni_1)
        print(eni_2)
        print("eni_1 == eni_2 ?=> {}".format(
            eni_1 == eni_2))

    y = curtin_config.load_config(sys.argv[1])
    network_config = y.get('network')
    test_parse(network_config)
    test_dump_and_load(network_config)
    test_output(network_config)
