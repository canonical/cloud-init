# This file is part of cloud-init.  See LICENSE file ...

import copy
import os

from . import renderer
from .network_state import subnet_is_ipv6, NET_CONFIG_TO_V2

from cloudinit import log as logging
from cloudinit import util
from cloudinit.net import SYS_CLASS_NET, get_devicelist

KNOWN_SNAPD_CONFIG = b"""\
# This is the initial network config.
# It can be overwritten by cloud-init or console-conf.
network:
    version: 2
    ethernets:
        all-en:
            match:
                name: "en*"
            dhcp4: true
        all-eth:
            match:
                name: "eth*"
            dhcp4: true
"""

LOG = logging.getLogger(__name__)


def _get_params_dict_by_match(config, match):
    return dict((key, value) for (key, value) in config.items()
                if key.startswith(match))


def _extract_addresses(config, entry, ifname):
    """This method parse a cloudinit.net.network_state dictionary (config) and
       maps netstate keys/values into a dictionary (entry) to represent
       netplan yaml.

    An example config dictionary might look like:

    {'mac_address': '52:54:00:12:34:00',
     'name': 'interface0',
     'subnets': [
        {'address': '192.168.1.2/24',
         'mtu': 1501,
         'type': 'static'},
        {'address': '2001:4800:78ff:1b:be76:4eff:fe06:1000",
         'mtu': 1480,
         'netmask': 64,
         'type': 'static'}],
      'type: physical'
    }

    An entry dictionary looks like:

    {'set-name': 'interface0',
     'match': {'macaddress': '52:54:00:12:34:00'},
     'mtu': 1501}

    After modification returns

    {'set-name': 'interface0',
     'match': {'macaddress': '52:54:00:12:34:00'},
     'mtu': 1501,
     'address': ['192.168.1.2/24', '2001:4800:78ff:1b:be76:4eff:fe06:1000"],
     'mtu6': 1480}

    """

    def _listify(obj, token=' '):
        "Helper to convert strings to list of strings, handle single string"
        if not obj or type(obj) not in [str]:
            return obj
        if token in obj:
            return obj.split(token)
        else:
            return [obj, ]

    addresses = []
    routes = []
    nameservers = []
    searchdomains = []
    subnets = config.get('subnets', [])
    if subnets is None:
        subnets = []
    for subnet in subnets:
        sn_type = subnet.get('type')
        if sn_type.startswith('dhcp'):
            if sn_type == 'dhcp':
                sn_type += '4'
            entry.update({sn_type: True})
        elif sn_type in ['static']:
            addr = "%s" % subnet.get('address')
            if 'prefix' in subnet:
                addr += "/%d" % subnet.get('prefix')
            if 'gateway' in subnet and subnet.get('gateway'):
                gateway = subnet.get('gateway')
                if ":" in gateway:
                    entry.update({'gateway6': gateway})
                else:
                    entry.update({'gateway4': gateway})
            if 'dns_nameservers' in subnet:
                nameservers += _listify(subnet.get('dns_nameservers', []))
            if 'dns_search' in subnet:
                searchdomains += _listify(subnet.get('dns_search', []))
            if 'mtu' in subnet:
                mtukey = 'mtu'
                if subnet_is_ipv6(subnet):
                    mtukey += '6'
                entry.update({mtukey: subnet.get('mtu')})
            for route in subnet.get('routes', []):
                to_net = "%s/%s" % (route.get('network'),
                                    route.get('prefix'))
                route = {
                    'via': route.get('gateway'),
                    'to': to_net,
                }
                if 'metric' in route:
                    route.update({'metric': route.get('metric', 100)})
                routes.append(route)

            addresses.append(addr)

    if 'mtu' in config:
        entry_mtu = entry.get('mtu')
        if entry_mtu and config['mtu'] != entry_mtu:
            LOG.warning(
                "Network config: ignoring %s device-level mtu:%s because"
                " ipv4 subnet-level mtu:%s provided.",
                ifname, config['mtu'], entry_mtu)
        else:
            entry['mtu'] = config['mtu']
    if len(addresses) > 0:
        entry.update({'addresses': addresses})
    if len(routes) > 0:
        entry.update({'routes': routes})
    if len(nameservers) > 0:
        ns = {'addresses': nameservers}
        entry.update({'nameservers': ns})
    if len(searchdomains) > 0:
        ns = entry.get('nameservers', {})
        ns.update({'search': searchdomains})
        entry.update({'nameservers': ns})


def _extract_bond_slaves_by_name(interfaces, entry, bond_master):
    bond_slave_names = sorted([name for (name, cfg) in interfaces.items()
                               if cfg.get('bond-master', None) == bond_master])
    if len(bond_slave_names) > 0:
        entry.update({'interfaces': bond_slave_names})


def _clean_default(target=None):
    # clean out any known default files and derived files in target
    # LP: #1675576
    tpath = util.target_path(target, "etc/netplan/00-snapd-config.yaml")
    if not os.path.isfile(tpath):
        return
    content = util.load_file(tpath, decode=False)
    if content != KNOWN_SNAPD_CONFIG:
        return

    derived = [util.target_path(target, f) for f in (
               'run/systemd/network/10-netplan-all-en.network',
               'run/systemd/network/10-netplan-all-eth.network',
               'run/systemd/generator/netplan.stamp')]
    existing = [f for f in derived if os.path.isfile(f)]
    LOG.debug("removing known config '%s' and derived existing files: %s",
              tpath, existing)

    for f in [tpath] + existing:
        os.unlink(f)


class Renderer(renderer.Renderer):
    """Renders network information in a /etc/netplan/network.yaml format."""

    NETPLAN_GENERATE = ['netplan', 'generate']

    def __init__(self, config=None):
        if not config:
            config = {}
        self.netplan_path = config.get('netplan_path',
                                       'etc/netplan/50-cloud-init.yaml')
        self.netplan_header = config.get('netplan_header', None)
        self._postcmds = config.get('postcmds', False)
        self.clean_default = config.get('clean_default', True)

    def render_network_state(self, network_state, target):
        # check network state for version
        # if v2, then extract network_state.config
        # else render_v2_from_state
        fpnplan = os.path.join(util.target_path(target), self.netplan_path)

        util.ensure_dir(os.path.dirname(fpnplan))
        header = self.netplan_header if self.netplan_header else ""

        # render from state
        content = self._render_content(network_state)

        if not header.endswith("\n"):
            header += "\n"
        util.write_file(fpnplan, header + content)

        if self.clean_default:
            _clean_default(target=target)
        self._netplan_generate(run=self._postcmds)
        self._net_setup_link(run=self._postcmds)

    def _netplan_generate(self, run=False):
        if not run:
            LOG.debug("netplan generate postcmd disabled")
            return
        util.subp(self.NETPLAN_GENERATE, capture=True)

    def _net_setup_link(self, run=False):
        """To ensure device link properties are applied, we poke
           udev to re-evaluate networkd .link files and call
           the setup_link udev builtin command
        """
        if not run:
            LOG.debug("netplan net_setup_link postcmd disabled")
            return
        setup_lnk = ['udevadm', 'test-builtin', 'net_setup_link']
        for cmd in [setup_lnk + [SYS_CLASS_NET + iface]
                    for iface in get_devicelist() if
                    os.path.islink(SYS_CLASS_NET + iface)]:
            util.subp(cmd, capture=True)

    def _render_content(self, network_state):

        # if content already in netplan format, pass it back
        if network_state.version == 2:
            LOG.debug('V2 to V2 passthrough')
            return util.yaml_dumps({'network': network_state.config},
                                   explicit_start=False,
                                   explicit_end=False)

        ethernets = {}
        wifis = {}
        bridges = {}
        bonds = {}
        vlans = {}
        content = []

        interfaces = network_state._network_state.get('interfaces', [])

        nameservers = network_state.dns_nameservers
        searchdomains = network_state.dns_searchdomains

        for config in network_state.iter_interfaces():
            ifname = config.get('name')
            # filter None (but not False) entries up front
            ifcfg = dict((key, value) for (key, value) in config.items()
                         if value is not None)

            if_type = ifcfg.get('type')
            if if_type == 'physical':
                # required_keys = ['name', 'mac_address']
                eth = {
                    'set-name': ifname,
                    'match': ifcfg.get('match', None),
                }
                if eth['match'] is None:
                    macaddr = ifcfg.get('mac_address', None)
                    if macaddr is not None:
                        eth['match'] = {'macaddress': macaddr.lower()}
                    else:
                        del eth['match']
                        del eth['set-name']
                _extract_addresses(ifcfg, eth, ifname)
                ethernets.update({ifname: eth})

            elif if_type == 'bond':
                # required_keys = ['name', 'bond_interfaces']
                bond = {}
                bond_config = {}
                # extract bond params and drop the bond_ prefix as it's
                # redundent in v2 yaml format
                v2_bond_map = NET_CONFIG_TO_V2.get('bond')
                for match in ['bond_', 'bond-']:
                    bond_params = _get_params_dict_by_match(ifcfg, match)
                    for (param, value) in bond_params.items():
                        newname = v2_bond_map.get(param.replace('_', '-'))
                        if newname is None:
                            continue
                        bond_config.update({newname: value})

                if len(bond_config) > 0:
                    bond.update({'parameters': bond_config})
                slave_interfaces = ifcfg.get('bond-slaves')
                if slave_interfaces == 'none':
                    _extract_bond_slaves_by_name(interfaces, bond, ifname)
                _extract_addresses(ifcfg, bond, ifname)
                bonds.update({ifname: bond})

            elif if_type == 'bridge':
                # required_keys = ['name', 'bridge_ports']
                ports = sorted(copy.copy(ifcfg.get('bridge_ports')))
                bridge = {
                    'interfaces': ports,
                }
                # extract bridge params and drop the bridge prefix as it's
                # redundent in v2 yaml format
                match_prefix = 'bridge_'
                params = _get_params_dict_by_match(ifcfg, match_prefix)
                br_config = {}

                # v2 yaml uses different names for the keys
                # and at least one value format change
                v2_bridge_map = NET_CONFIG_TO_V2.get('bridge')
                for (param, value) in params.items():
                    newname = v2_bridge_map.get(param)
                    if newname is None:
                        continue
                    br_config.update({newname: value})
                    if newname in ['path-cost', 'port-priority']:
                        # <interface> <value> -> <interface>: int(<value>)
                        newvalue = {}
                        for val in value:
                            (port, portval) = val.split()
                            newvalue[port] = int(portval)
                        br_config.update({newname: newvalue})

                if len(br_config) > 0:
                    bridge.update({'parameters': br_config})
                _extract_addresses(ifcfg, bridge, ifname)
                bridges.update({ifname: bridge})

            elif if_type == 'vlan':
                # required_keys = ['name', 'vlan_id', 'vlan-raw-device']
                vlan = {
                    'id': ifcfg.get('vlan_id'),
                    'link': ifcfg.get('vlan-raw-device')
                }
                macaddr = ifcfg.get('mac_address', None)
                if macaddr is not None:
                    vlan['macaddress'] = macaddr.lower()
                _extract_addresses(ifcfg, vlan, ifname)
                vlans.update({ifname: vlan})

        # inject global nameserver values under each all interface which
        # has addresses and do not already have a DNS configuration
        if nameservers or searchdomains:
            nscfg = {'addresses': nameservers, 'search': searchdomains}
            for section in [ethernets, wifis, bonds, bridges, vlans]:
                for _name, cfg in section.items():
                    if 'nameservers' in cfg or 'addresses' not in cfg:
                        continue
                    cfg.update({'nameservers': nscfg})

        # workaround yaml dictionary key sorting when dumping
        def _render_section(name, section):
            if section:
                dump = util.yaml_dumps({name: section},
                                       explicit_start=False,
                                       explicit_end=False)
                txt = util.indent(dump, ' ' * 4)
                return [txt]
            return []

        content.append("network:\n    version: 2\n")
        content += _render_section('ethernets', ethernets)
        content += _render_section('wifis', wifis)
        content += _render_section('bonds', bonds)
        content += _render_section('bridges', bridges)
        content += _render_section('vlans', vlans)

        return "".join(content)


def available(target=None):
    expected = ['netplan']
    search = ['/usr/sbin', '/sbin']
    for p in expected:
        if not util.which(p, search=search, target=target):
            return False
    return True


def network_state_to_netplan(network_state, header=None):
    # render the provided network state, return a string of equivalent eni
    netplan_path = 'etc/network/50-cloud-init.yaml'
    renderer = Renderer({
        'netplan_path': netplan_path,
        'netplan_header': header,
    })
    if not header:
        header = ""
    if not header.endswith("\n"):
        header += "\n"
    contents = renderer._render_content(network_state)
    return header + contents

# vi: ts=4 expandtab
