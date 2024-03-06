# Copyright (C) 2017 Canonical Ltd.
#
# Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import functools
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from cloudinit import safeyaml, util
from cloudinit.net import (
    find_interface_name_from_mac,
    get_interfaces_by_mac,
    ipv4_mask_to_net_prefix,
    ipv6_mask_to_net_prefix,
    is_ip_network,
    is_ipv4_network,
    is_ipv6_address,
    is_ipv6_network,
    net_prefix_to_ipv4_mask,
)

if TYPE_CHECKING:
    from cloudinit.net.renderer import Renderer

LOG = logging.getLogger(__name__)

NETWORK_STATE_VERSION = 1
NETWORK_STATE_REQUIRED_KEYS = {
    1: ["version", "config", "network_state"],
}
NETWORK_V2_KEY_FILTER = [
    "addresses",
    "dhcp4",
    "dhcp4-overrides",
    "dhcp6",
    "dhcp6-overrides",
    "gateway4",
    "gateway6",
    "interfaces",
    "match",
    "mtu",
    "nameservers",
    "renderer",
    "set-name",
    "wakeonlan",
    "accept-ra",
]

NET_CONFIG_TO_V2: Dict[str, Dict[str, Any]] = {
    "bond": {
        "bond-ad-select": "ad-select",
        "bond-arp-interval": "arp-interval",
        "bond-arp-ip-target": "arp-ip-target",
        "bond-arp-validate": "arp-validate",
        "bond-downdelay": "down-delay",
        "bond-fail-over-mac": "fail-over-mac-policy",
        "bond-lacp-rate": "lacp-rate",
        "bond-miimon": "mii-monitor-interval",
        "bond-min-links": "min-links",
        "bond-mode": "mode",
        "bond-num-grat-arp": "gratuitous-arp",
        "bond-primary": "primary",
        "bond-primary-reselect": "primary-reselect-policy",
        "bond-updelay": "up-delay",
        "bond-xmit-hash-policy": "transmit-hash-policy",
    },
    "bridge": {
        "bridge_ageing": "ageing-time",
        "bridge_bridgeprio": "priority",
        "bridge_fd": "forward-delay",
        "bridge_gcint": None,
        "bridge_hello": "hello-time",
        "bridge_maxage": "max-age",
        "bridge_maxwait": None,
        "bridge_pathcost": "path-cost",
        "bridge_portprio": "port-priority",
        "bridge_stp": "stp",
        "bridge_waitport": None,
    },
}


def warn_deprecated_all_devices(dikt: dict) -> None:
    """Warn about deprecations of v2 properties for all devices"""
    if "gateway4" in dikt or "gateway6" in dikt:
        util.deprecate(
            deprecated="The use of `gateway4` and `gateway6`",
            deprecated_version="22.4",
            extra_message="For more info check out: "
            "https://cloudinit.readthedocs.io/en/latest/topics/network-config-format-v2.html",  # noqa: E501
        )


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
                    raise InvalidCommand(
                        "Command missing %s of required keys %s"
                        % (missing_keys, required_keys)
                    )
            return func(self, command, *args, **kwargs)

        return decorator

    return wrapper


class NetworkState:
    def __init__(
        self, network_state: dict, version: int = NETWORK_STATE_VERSION
    ):
        self._network_state = copy.deepcopy(network_state)
        self._version = version
        self.use_ipv6 = network_state.get("use_ipv6", False)
        self._has_default_route = None

    @property
    def config(self) -> dict:
        return self._network_state["config"]

    @property
    def version(self):
        return self._version

    @property
    def dns_nameservers(self):
        try:
            return self._network_state["dns"]["nameservers"]
        except KeyError:
            return []

    @property
    def dns_searchdomains(self):
        try:
            return self._network_state["dns"]["search"]
        except KeyError:
            return []

    @property
    def has_default_route(self):
        if self._has_default_route is None:
            self._has_default_route = self._maybe_has_default_route()
        return self._has_default_route

    def iter_interfaces(self, filter_func=None):
        ifaces = self._network_state.get("interfaces", {})
        for iface in ifaces.values():
            if filter_func is None:
                yield iface
            else:
                if filter_func(iface):
                    yield iface

    def iter_routes(self, filter_func=None):
        for route in self._network_state.get("routes", []):
            if filter_func is not None:
                if filter_func(route):
                    yield route
            else:
                yield route

    def _maybe_has_default_route(self):
        for route in self.iter_routes():
            if self._is_default_route(route):
                return True
        for iface in self.iter_interfaces():
            for subnet in iface.get("subnets", []):
                for route in subnet.get("routes", []):
                    if self._is_default_route(route):
                        return True
        return False

    def _is_default_route(self, route):
        default_nets = ("::", "0.0.0.0")
        return (
            route.get("prefix") == 0 and route.get("network") in default_nets
        )

    @classmethod
    def to_passthrough(cls, network_state: dict) -> "NetworkState":
        """Instantiates a `NetworkState` without interpreting its data.

        That means only `config` and `version` are copied.

        :param network_state: Network state data.
        :return: Instance of `NetworkState`.
        """
        kwargs = {}
        if "version" in network_state:
            kwargs["version"] = network_state["version"]
        return cls({"config": network_state}, **kwargs)


class NetworkStateInterpreter:
    initial_network_state = {
        "interfaces": {},
        "routes": [],
        "dns": {
            "nameservers": [],
            "search": [],
        },
        "use_ipv6": False,
        "config": None,
    }

    def __init__(
        self,
        version=NETWORK_STATE_VERSION,
        config=None,
        renderer: "Optional[Renderer]" = None,
    ):
        self._version = version
        self._config = config
        self._network_state = copy.deepcopy(self.initial_network_state)
        self._network_state["config"] = config
        self._parsed = False
        self._interface_dns_map: dict = {}
        self._renderer = renderer
        self.command_handlers = {
            "bond": self.handle_bond,
            "bonds": self.handle_bonds,
            "bridge": self.handle_bridge,
            "bridges": self.handle_bridges,
            "ethernets": self.handle_ethernets,
            "infiniband": self.handle_infiniband,
            "loopback": self.handle_loopback,
            "nameserver": self.handle_nameserver,
            "physical": self.handle_physical,
            "route": self.handle_route,
            "vlan": self.handle_vlan,
            "vlans": self.handle_vlans,
            "wifis": self.handle_wifis,
        }

    @property
    def network_state(self) -> NetworkState:
        from cloudinit.net.netplan import Renderer as NetplanRenderer

        if self._version == 2 and isinstance(self._renderer, NetplanRenderer):
            LOG.debug("Passthrough netplan v2 config")
            return NetworkState.to_passthrough(self._config)
        return NetworkState(self._network_state, version=self._version)

    @property
    def use_ipv6(self):
        return self._network_state.get("use_ipv6")

    @use_ipv6.setter
    def use_ipv6(self, val):
        self._network_state.update({"use_ipv6": val})

    def dump(self):
        state = {
            "version": self._version,
            "config": self._config,
            "network_state": self._network_state,
        }
        return safeyaml.dumps(state)

    def load(self, state):
        if "version" not in state:
            LOG.error("Invalid state, missing version field")
            raise ValueError("Invalid state, missing version field")

        required_keys = NETWORK_STATE_REQUIRED_KEYS[state["version"]]
        missing_keys = diff_keys(required_keys, state)
        if missing_keys:
            msg = "Invalid state, missing keys: %s" % (missing_keys)
            LOG.error(msg)
            raise ValueError(msg)

        # v1 - direct attr mapping, except version
        for key in [k for k in required_keys if k not in ["version"]]:
            setattr(self, key, state[key])

    def dump_network_state(self):
        return safeyaml.dumps(self._network_state)

    def as_dict(self):
        return {"version": self._version, "config": self._config}

    def parse_config(self, skip_broken=True):
        if self._version == 1:
            self.parse_config_v1(skip_broken=skip_broken)
            self._parsed = True
        elif self._version == 2:
            self.parse_config_v2(skip_broken=skip_broken)
            self._parsed = True

    def parse_config_v1(self, skip_broken=True):
        for command in self._config:
            command_type = command["type"]
            try:
                handler = self.command_handlers[command_type]
            except KeyError as e:
                raise RuntimeError(
                    "No handler found for  command '%s'" % command_type
                ) from e
            try:
                handler(command)
            except InvalidCommand:
                if not skip_broken:
                    raise
                else:
                    LOG.warning(
                        "Skipping invalid command: %s", command, exc_info=True
                    )
                    LOG.debug(self.dump_network_state())
        for interface, dns in self._interface_dns_map.items():
            iface = None
            try:
                iface = self._network_state["interfaces"][interface]
            except KeyError as e:
                raise ValueError(
                    "Nameserver specified for interface {0}, "
                    "but interface {0} does not exist!".format(interface)
                ) from e
            if iface:
                nameservers, search = dns
                iface["dns"] = {
                    "nameservers": nameservers,
                    "search": search,
                }

    def parse_config_v2(self, skip_broken=True):
        from cloudinit.net.netplan import Renderer as NetplanRenderer

        if isinstance(self._renderer, NetplanRenderer):
            # Nothing to parse as we are going to perform a Netplan passthrough
            return

        for command_type, command in self._config.items():
            if command_type in ["version", "renderer"]:
                continue
            try:
                handler = self.command_handlers[command_type]
            except KeyError as e:
                raise RuntimeError(
                    "No handler found for command '%s'" % command_type
                ) from e
            try:
                handler(command)
                self._v2_common(command)
            except InvalidCommand:
                if not skip_broken:
                    raise
                else:
                    LOG.warning(
                        "Skipping invalid command: %s", command, exc_info=True
                    )
                    LOG.debug(self.dump_network_state())

    @ensure_command_keys(["name"])
    def handle_loopback(self, command):
        return self.handle_physical(command)

    @ensure_command_keys(["name"])
    def handle_physical(self, command):
        """
        command = {
            'type': 'physical',
            'mac_address': 'c0:d6:9f:2c:e8:80',
            'name': 'eth0',
            'subnets': [
                {'type': 'dhcp4'}
             ],
            'accept-ra': 'true'
        }
        """

        interfaces = self._network_state.get("interfaces", {})
        iface = interfaces.get(command["name"], {})
        for param, val in command.get("params", {}).items():
            iface.update({param: val})

        # convert subnet ipv6 netmask to cidr as needed
        subnets = _normalize_subnets(command.get("subnets"))

        # automatically set 'use_ipv6' if any addresses are ipv6
        if not self.use_ipv6:
            for subnet in subnets:
                if subnet.get("type").endswith("6") or is_ipv6_address(
                    subnet.get("address")
                ):
                    self.use_ipv6 = True
                    break

        accept_ra = command.get("accept-ra", None)
        if accept_ra is not None:
            accept_ra = util.is_true(accept_ra)
        wakeonlan = command.get("wakeonlan", None)
        if wakeonlan is not None:
            wakeonlan = util.is_true(wakeonlan)
        iface.update(
            {
                "name": command.get("name"),
                "type": command.get("type"),
                "mac_address": command.get("mac_address"),
                "inet": "inet",
                "mode": "manual",
                "mtu": command.get("mtu"),
                "address": None,
                "gateway": None,
                "subnets": subnets,
                "accept-ra": accept_ra,
                "wakeonlan": wakeonlan,
            }
        )
        self._network_state["interfaces"].update({command.get("name"): iface})
        self.dump_network_state()

    @ensure_command_keys(["name", "vlan_id", "vlan_link"])
    def handle_vlan(self, command):
        """
        auto eth0.222
        iface eth0.222 inet static
                address 10.10.10.1
                netmask 255.255.255.0
                hwaddress ether BC:76:4E:06:96:B3
                vlan-raw-device eth0
        """
        interfaces = self._network_state.get("interfaces", {})
        self.handle_physical(command)
        iface = interfaces.get(command.get("name"), {})
        iface["vlan-raw-device"] = command.get("vlan_link")
        iface["vlan_id"] = command.get("vlan_id")
        interfaces.update({iface["name"]: iface})

    @ensure_command_keys(["name", "bond_interfaces", "params"])
    def handle_bond(self, command):
        """
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
        """

        self.handle_physical(command)
        interfaces = self._network_state.get("interfaces")
        iface = interfaces.get(command.get("name"), {})
        for param, val in command.get("params").items():
            iface.update({param: val})
        iface.update({"bond-slaves": "none"})
        self._network_state["interfaces"].update({iface["name"]: iface})

        # handle bond slaves
        for ifname in command.get("bond_interfaces"):
            if ifname not in interfaces:
                cmd = {
                    "name": ifname,
                    "type": "bond",
                }
                # inject placeholder
                self.handle_physical(cmd)

            interfaces = self._network_state.get("interfaces", {})
            bond_if = interfaces.get(ifname)
            bond_if["bond-master"] = command.get("name")
            # copy in bond config into slave
            for param, val in command.get("params").items():
                bond_if.update({param: val})
            self._network_state["interfaces"].update({ifname: bond_if})

    @ensure_command_keys(["name", "bridge_interfaces"])
    def handle_bridge(self, command):
        """
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
        """

        # find one of the bridge port ifaces to get mac_addr
        # handle bridge_slaves
        interfaces = self._network_state.get("interfaces", {})
        for ifname in command.get("bridge_interfaces"):
            if ifname in interfaces:
                continue

            cmd = {
                "name": ifname,
            }
            # inject placeholder
            self.handle_physical(cmd)

        interfaces = self._network_state.get("interfaces", {})
        self.handle_physical(command)
        iface = interfaces.get(command.get("name"), {})
        iface["bridge_ports"] = command["bridge_interfaces"]
        for param, val in command.get("params", {}).items():
            iface.update({param: val})

        # convert value to boolean
        bridge_stp = iface.get("bridge_stp")
        if bridge_stp is not None and not isinstance(bridge_stp, bool):
            if bridge_stp in ["on", "1", 1]:
                bridge_stp = True
            elif bridge_stp in ["off", "0", 0]:
                bridge_stp = False
            else:
                raise ValueError(
                    "Cannot convert bridge_stp value ({stp}) to"
                    " boolean".format(stp=bridge_stp)
                )
            iface.update({"bridge_stp": bridge_stp})

        interfaces.update({iface["name"]: iface})

    @ensure_command_keys(["name"])
    def handle_infiniband(self, command):
        self.handle_physical(command)

    def _parse_dns(self, command):
        nameservers = []
        search = []
        if "address" in command:
            addrs = command["address"]
            if not isinstance(addrs, list):
                addrs = [addrs]
            for addr in addrs:
                nameservers.append(addr)
        if "search" in command:
            paths = command["search"]
            if not isinstance(paths, list):
                paths = [paths]
            for path in paths:
                search.append(path)
        return nameservers, search

    @ensure_command_keys(["address"])
    def handle_nameserver(self, command):
        dns = self._network_state.get("dns")
        nameservers, search = self._parse_dns(command)
        if "interface" in command:
            self._interface_dns_map[command["interface"]] = (
                nameservers,
                search,
            )
        else:
            dns["nameservers"].extend(nameservers)
            dns["search"].extend(search)

    @ensure_command_keys(["address"])
    def _handle_individual_nameserver(self, command, iface):
        _iface = self._network_state.get("interfaces")
        nameservers, search = self._parse_dns(command)
        _iface[iface]["dns"] = {"nameservers": nameservers, "search": search}

    @ensure_command_keys(["destination"])
    def handle_route(self, command):
        self._network_state["routes"].append(_normalize_route(command))

    # V2 handlers
    def handle_bonds(self, command):
        """
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

        """
        self._handle_bond_bridge(command, cmd_type="bond")

    def handle_bridges(self, command):
        """
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

        """
        self._handle_bond_bridge(command, cmd_type="bridge")

    def handle_ethernets(self, command):
        """
        ethernets:
          eno1:
            match:
              macaddress: 00:11:22:33:44:55
              driver: hv_netvsc
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
            accept-ra: true
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
        """

        # Get the interfaces by MAC address to update an interface's
        # device name to the name of the device that matches a provided
        # MAC address when the set-name directive is not present.
        #
        # Please see https://bugs.launchpad.net/cloud-init/+bug/1855945
        # for more information.
        ifaces_by_mac = get_interfaces_by_mac()

        for eth, cfg in command.items():
            phy_cmd = {
                "type": "physical",
            }
            match = cfg.get("match", {})
            mac_address = match.get("macaddress", None)
            if not mac_address:
                LOG.debug(
                    'NetworkState Version2: missing "macaddress" info '
                    "in config entry: %s: %s",
                    eth,
                    str(cfg),
                )
            phy_cmd["mac_address"] = mac_address

            # Determine the name of the interface by using one of the
            # following in the order they are listed:
            #   * set-name
            #   * interface name looked up by mac
            #   * value of "eth" key from this loop
            name = eth
            set_name = cfg.get("set-name")
            if set_name:
                name = set_name
            elif mac_address and ifaces_by_mac:
                lcase_mac_address = mac_address.lower()
                mac = find_interface_name_from_mac(lcase_mac_address)
                if mac:
                    name = mac
            phy_cmd["name"] = name

            driver = match.get("driver", None)
            if driver:
                phy_cmd["params"] = {"driver": driver}
            for key in ["mtu", "match", "wakeonlan", "accept-ra"]:
                if key in cfg:
                    phy_cmd[key] = cfg[key]

            warn_deprecated_all_devices(cfg)

            subnets = self._v2_to_v1_ipcfg(cfg)
            if len(subnets) > 0:
                phy_cmd.update({"subnets": subnets})

            LOG.debug("v2(ethernets) -> v1(physical):\n%s", phy_cmd)
            self.handle_physical(phy_cmd)

    def handle_vlans(self, command):
        """
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
        """
        for vlan, cfg in command.items():
            vlan_cmd = {
                "type": "vlan",
                "name": vlan,
                "vlan_id": cfg.get("id"),
                "vlan_link": cfg.get("link"),
            }
            if "mtu" in cfg:
                vlan_cmd["mtu"] = cfg["mtu"]
            warn_deprecated_all_devices(cfg)
            subnets = self._v2_to_v1_ipcfg(cfg)
            if len(subnets) > 0:
                vlan_cmd.update({"subnets": subnets})
            LOG.debug("v2(vlans) -> v1(vlan):\n%s", vlan_cmd)
            self.handle_vlan(vlan_cmd)

    def handle_wifis(self, command):
        LOG.warning(
            "Wifi configuration is only available to distros with"
            " netplan rendering support."
        )

    def _v2_common(self, cfg) -> None:
        LOG.debug("v2_common: handling config:\n%s", cfg)
        for iface, dev_cfg in cfg.items():
            if "set-name" in dev_cfg:
                set_name_iface = dev_cfg.get("set-name")
                if set_name_iface:
                    iface = set_name_iface
            if "nameservers" in dev_cfg:
                search = dev_cfg.get("nameservers").get("search", [])
                dns = dev_cfg.get("nameservers").get("addresses", [])
                name_cmd = {"type": "nameserver"}
                if len(search) > 0:
                    name_cmd.update({"search": search})
                if len(dns) > 0:
                    name_cmd.update({"address": dns})

                mac_address: Optional[str] = dev_cfg.get("match", {}).get(
                    "macaddress"
                )
                if mac_address:
                    real_if_name = find_interface_name_from_mac(mac_address)
                    if real_if_name:
                        iface = real_if_name

                self._handle_individual_nameserver(name_cmd, iface)

    def _handle_bond_bridge(self, command, cmd_type=None):
        """Common handler for bond and bridge types"""

        # inverse mapping for v2 keynames to v1 keynames
        v2key_to_v1 = dict(
            (v, k) for k, v in NET_CONFIG_TO_V2.get(cmd_type).items()
        )

        for item_name, item_cfg in command.items():
            item_params = dict(
                (key, value)
                for (key, value) in item_cfg.items()
                if key not in NETWORK_V2_KEY_FILTER
            )
            # We accept both spellings (as netplan does).  LP: #1756701
            # Normalize internally to the new spelling:
            params = item_params.get("parameters", {})
            grat_value = params.pop("gratuitious-arp", None)
            if grat_value:
                params["gratuitous-arp"] = grat_value

            v1_cmd = {
                "type": cmd_type,
                "name": item_name,
                cmd_type + "_interfaces": item_cfg.get("interfaces"),
                "params": dict((v2key_to_v1[k], v) for k, v in params.items()),
            }
            if "mtu" in item_cfg:
                v1_cmd["mtu"] = item_cfg["mtu"]

            warn_deprecated_all_devices(item_cfg)
            subnets = self._v2_to_v1_ipcfg(item_cfg)
            if len(subnets) > 0:
                v1_cmd.update({"subnets": subnets})

            LOG.debug("v2(%s) -> v1(%s):\n%s", cmd_type, cmd_type, v1_cmd)
            if cmd_type == "bridge":
                self.handle_bridge(v1_cmd)
            elif cmd_type == "bond":
                self.handle_bond(v1_cmd)
            else:
                raise ValueError(
                    "Unknown command type: {cmd_type}".format(
                        cmd_type=cmd_type
                    )
                )

    def _v2_to_v1_ipcfg(self, cfg):
        """Common ipconfig extraction from v2 to v1 subnets array."""

        def _add_dhcp_overrides(overrides, subnet):
            if "route-metric" in overrides:
                subnet["metric"] = overrides["route-metric"]

        subnets = []
        if cfg.get("dhcp4"):
            subnet = {"type": "dhcp4"}
            _add_dhcp_overrides(cfg.get("dhcp4-overrides", {}), subnet)
            subnets.append(subnet)
        if cfg.get("dhcp6"):
            subnet = {"type": "dhcp6"}
            self.use_ipv6 = True
            _add_dhcp_overrides(cfg.get("dhcp6-overrides", {}), subnet)
            subnets.append(subnet)

        gateway4 = None
        gateway6 = None
        nameservers = {}
        for address in cfg.get("addresses", []):
            subnet = {
                "type": "static",
                "address": address,
            }

            if ":" in address:
                if "gateway6" in cfg and gateway6 is None:
                    gateway6 = cfg.get("gateway6")
                    subnet.update({"gateway": gateway6})
            else:
                if "gateway4" in cfg and gateway4 is None:
                    gateway4 = cfg.get("gateway4")
                    subnet.update({"gateway": gateway4})

            if "nameservers" in cfg and not nameservers:
                addresses = cfg.get("nameservers").get("addresses")
                if addresses:
                    nameservers["dns_nameservers"] = addresses
                search = cfg.get("nameservers").get("search")
                if search:
                    nameservers["dns_search"] = search
                subnet.update(nameservers)

            subnets.append(subnet)

        routes = []
        for route in cfg.get("routes", []):
            routes.append(
                _normalize_route(
                    {
                        "destination": route.get("to"),
                        "gateway": route.get("via"),
                        "metric": route.get("metric"),
                        "mtu": route.get("mtu"),
                    }
                )
            )

        # v2 routes are bound to the interface, in v1 we add them under
        # the first subnet since there isn't an equivalent interface level.
        if len(subnets) and len(routes):
            subnets[0]["routes"] = routes

        return subnets


def _normalize_subnet(subnet):
    # Prune all keys with None values.
    subnet = copy.deepcopy(subnet)
    normal_subnet = dict((k, v) for k, v in subnet.items() if v)

    if subnet.get("type") in ("static", "static6"):
        normal_subnet.update(
            _normalize_net_keys(
                normal_subnet,
                address_keys=(
                    "address",
                    "ip_address",
                ),
            )
        )
    normal_subnet["routes"] = [
        _normalize_route(r) for r in subnet.get("routes", [])
    ]

    def listify(snet, name):
        if name in snet and not isinstance(snet[name], list):
            snet[name] = snet[name].split()

    for k in ("dns_search", "dns_nameservers"):
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
    net = {k: v for k, v in network.items() if v or v == 0}
    addr_key = None
    for key in address_keys:
        if net.get(key):
            addr_key = key
            break
    if not addr_key:
        message = "No config network address keys [%s] found in %s" % (
            ",".join(address_keys),
            network,
        )
        LOG.error(message)
        raise ValueError(message)

    addr = str(net.get(addr_key))
    if not is_ip_network(addr):
        LOG.error("Address %s is not a valid ip network", addr)
        raise ValueError(f"Address {addr} is not a valid ip address")

    ipv6 = is_ipv6_network(addr)
    ipv4 = is_ipv4_network(addr)

    netmask = net.get("netmask")
    if "/" in addr:
        addr_part, _, maybe_prefix = addr.partition("/")
        net[addr_key] = addr_part
        if ipv6:
            # this supports input of ffff:ffff:ffff::
            prefix = ipv6_mask_to_net_prefix(maybe_prefix)
        elif ipv4:
            # this supports input of 255.255.255.0
            prefix = ipv4_mask_to_net_prefix(maybe_prefix)
        else:
            # In theory this never happens, is_ip_network() should catch all
            # invalid networks
            LOG.error("Address %s is not a valid ip network", addr)
            raise ValueError(f"Address {addr} is not a valid ip address")
    elif "prefix" in net:
        prefix = int(net["prefix"])
    elif netmask and ipv4:
        prefix = ipv4_mask_to_net_prefix(netmask)
    elif netmask and ipv6:
        prefix = ipv6_mask_to_net_prefix(netmask)
    else:
        prefix = 64 if ipv6 else 24

    if "prefix" in net and str(net["prefix"]) != str(prefix):
        LOG.warning(
            "Overwriting existing 'prefix' with '%s' in network info: %s",
            prefix,
            net,
        )
    net["prefix"] = prefix

    if ipv6:
        # TODO: we could/maybe should add this back with the very uncommon
        # 'netmask' for ipv6.  We need a 'net_prefix_to_ipv6_mask' for that.
        if "netmask" in net:
            del net["netmask"]
    elif ipv4:
        net["netmask"] = net_prefix_to_ipv4_mask(net["prefix"])

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
    normal_route = dict(
        (k, v) for k, v in route.items() if v not in ("", None)
    )
    if "destination" in normal_route:
        normal_route["network"] = normal_route["destination"]
        del normal_route["destination"]

    normal_route.update(
        _normalize_net_keys(
            normal_route, address_keys=("network", "destination")
        )
    )

    metric = normal_route.get("metric")
    if metric:
        try:
            normal_route["metric"] = int(metric)
        except ValueError as e:
            raise TypeError(
                "Route config metric {} is not an integer".format(metric)
            ) from e
    return normal_route


def _normalize_subnets(subnets):
    if not subnets:
        subnets = []
    return [_normalize_subnet(s) for s in subnets]


def parse_net_config_data(
    net_config: dict,
    skip_broken: bool = True,
    renderer=None,  # type: Optional[Renderer]
) -> NetworkState:
    """Parses the config, returns NetworkState object

    :param net_config: curtin network config dict
    """
    state = None
    version = net_config.get("version")
    config = net_config.get("config")
    if version == 2:
        # v2 does not have explicit 'config' key so we
        # pass the whole net-config as-is
        config = net_config

    if version and config is not None:
        nsi = NetworkStateInterpreter(
            version=version, config=config, renderer=renderer
        )
        nsi.parse_config(skip_broken=skip_broken)
        state = nsi.network_state

    if not state:
        raise RuntimeError(
            "No valid network_state object created from network config. "
            "Did you specify the correct version? Network config:\n"
            f"{net_config}"
        )

    return state
