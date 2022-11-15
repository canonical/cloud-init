# Copyright 2022 Red Hat, Inc.
#
# Author: Lubomir Rintel <lkundrak@v3.sk>
# Fixes and suggestions contributed by James Falcon, Neal Gompa,
# Zbigniew Jędrzejewski-Szmek and Emanuele Giuseppe Esposito.
#
# This file is part of cloud-init. See LICENSE file for license information.

import configparser
import io
import itertools
import os
import uuid
from typing import Optional

from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.net import is_ipv6_address, renderer, subnet_is_ipv6
from cloudinit.net.network_state import NetworkState

NM_RUN_DIR = "/etc/NetworkManager"
NM_LIB_DIR = "/usr/lib/NetworkManager"
NM_CFG_FILE = "/etc/NetworkManager/NetworkManager.conf"
LOG = logging.getLogger(__name__)


class NMConnection:
    """Represents a NetworkManager connection profile."""

    def __init__(self, con_id):
        """
        Initializes the connection with some very basic properties,
        notably the UUID so that the connection can be referred to.
        """

        # Chosen by fair dice roll
        CI_NM_UUID = uuid.UUID("a3924cb8-09e0-43e9-890b-77972a800108")

        self.config = configparser.ConfigParser()
        # Identity option name mapping, to achieve case sensitivity
        self.config.optionxform = str

        self.config["connection"] = {
            "id": f"cloud-init {con_id}",
            "uuid": str(uuid.uuid5(CI_NM_UUID, con_id)),
        }

        # This is not actually used anywhere, but may be useful in future
        self.config["user"] = {
            "org.freedesktop.NetworkManager.origin": "cloud-init"
        }

    def _set_default(self, section, option, value):
        """
        Sets a property unless it's already set, ensuring the section
        exists.
        """

        if not self.config.has_section(section):
            self.config[section] = {}
        if not self.config.has_option(section, option):
            self.config[section][option] = value

    def _set_ip_method(self, family, subnet_type):
        """
        Ensures there's appropriate [ipv4]/[ipv6] for given family
        appropriate for given configuration type
        """

        method_map = {
            "static": "manual",
            "dhcp6": "auto",
            "ipv6_slaac": "auto",
            "ipv6_dhcpv6-stateless": "auto",
            "ipv6_dhcpv6-stateful": "auto",
            "dhcp4": "auto",
            "dhcp": "auto",
        }

        # Ensure we got an [ipvX] section
        self._set_default(family, "method", "disabled")

        try:
            method = method_map[subnet_type]
        except KeyError:
            # What else can we do
            method = "auto"
            self.config[family]["may-fail"] = "true"

        # Make sure we don't "downgrade" the method in case
        # we got conflicting subnets (e.g. static along with dhcp)
        if self.config[family]["method"] == "dhcp":
            return
        if self.config[family]["method"] == "auto" and method == "manual":
            return

        self.config[family]["method"] = method
        self._set_default(family, "may-fail", "false")

    def _add_numbered(self, section, key_prefix, value):
        """
        Adds a numbered property, such as address<n> or route<n>, ensuring
        the appropriate value gets used for <n>.
        """

        for index in itertools.count(1):
            key = f"{key_prefix}{index}"
            if not self.config.has_option(section, key):
                self.config[section][key] = value
                break

    def _add_address(self, family, subnet):
        """
        Adds an ipv[46]address<n> property.
        """

        value = subnet["address"] + "/" + str(subnet["prefix"])
        self._add_numbered(family, "address", value)

    def _add_route(self, family, route):
        """
        Adds a ipv[46].route<n> property.
        """

        value = route["network"] + "/" + str(route["prefix"])
        if "gateway" in route:
            value = value + "," + route["gateway"]
        self._add_numbered(family, "route", value)

    def _add_nameserver(self, dns):
        """
        Extends the ipv[46].dns property with a name server.
        """

        # FIXME: the subnet contains IPv4 and IPv6 name server mixed
        # together. We might be getting an IPv6 name server while
        # we're dealing with an IPv4 subnet. Sort this out by figuring
        # out the correct family and making sure a valid section exist.
        family = "ipv6" if is_ipv6_address(dns) else "ipv4"
        self._set_default(family, "method", "disabled")

        self._set_default(family, "dns", "")
        self.config[family]["dns"] = self.config[family]["dns"] + dns + ";"

    def _add_dns_search(self, family, dns_search):
        """
        Extends the ipv[46].dns-search property with a name server.
        """

        self._set_default(family, "dns-search", "")
        self.config[family]["dns-search"] = (
            self.config[family]["dns-search"] + ";".join(dns_search) + ";"
        )

    def con_uuid(self):
        """
        Returns the connection UUID
        """
        return self.config["connection"]["uuid"]

    def valid(self):
        """
        Can this be serialized into a meaningful connection profile?
        """
        return self.config.has_option("connection", "type")

    @staticmethod
    def mac_addr(addr):
        """
        Sanitize a MAC address.
        """
        return addr.replace("-", ":").upper()

    def render_interface(self, iface, renderer):
        """
        Integrate information from network state interface information
        into the connection. Most of the work is done here.
        """

        # Initialize type & connectivity
        _type_map = {
            "physical": "ethernet",
            "vlan": "vlan",
            "bond": "bond",
            "bridge": "bridge",
            "infiniband": "infiniband",
            "loopback": None,
        }

        if_type = _type_map[iface["type"]]
        if if_type is None:
            return
        if "bond-master" in iface:
            slave_type = "bond"
        else:
            slave_type = None

        self.config["connection"]["type"] = if_type
        if slave_type is not None:
            self.config["connection"]["slave-type"] = slave_type
            self.config["connection"]["master"] = renderer.con_ref(
                iface[slave_type + "-master"]
            )

        # Add type specific-section
        self.config[if_type] = {}

        # These are the interface properties that map nicely
        # to NetworkManager properties
        _prop_map = {
            "bond": {
                "mode": "bond-mode",
                "miimon": "bond_miimon",
                "xmit_hash_policy": "bond-xmit-hash-policy",
                "num_grat_arp": "bond-num-grat-arp",
                "downdelay": "bond-downdelay",
                "updelay": "bond-updelay",
                "fail_over_mac": "bond-fail-over-mac",
                "primary_reselect": "bond-primary-reselect",
                "primary": "bond-primary",
            },
            "bridge": {
                "stp": "bridge_stp",
                "priority": "bridge_bridgeprio",
            },
            "vlan": {
                "id": "vlan_id",
            },
            "ethernet": {},
            "infiniband": {},
        }

        device_mtu = iface["mtu"]
        ipv4_mtu = None

        # Deal with Layer 3 configuration
        for subnet in iface["subnets"]:
            family = "ipv6" if subnet_is_ipv6(subnet) else "ipv4"

            self._set_ip_method(family, subnet["type"])
            if "address" in subnet:
                self._add_address(family, subnet)
            if "gateway" in subnet:
                self.config[family]["gateway"] = subnet["gateway"]
            for route in subnet["routes"]:
                self._add_route(family, route)
            if "dns_nameservers" in subnet:
                for nameserver in subnet["dns_nameservers"]:
                    self._add_nameserver(nameserver)
            if "dns_search" in subnet:
                self._add_dns_search(family, subnet["dns_search"])
            if family == "ipv4" and "mtu" in subnet:
                ipv4_mtu = subnet["mtu"]

        if ipv4_mtu is None:
            ipv4_mtu = device_mtu
        if not ipv4_mtu == device_mtu:
            LOG.warning(
                "Network config: ignoring %s device-level mtu:%s"
                " because ipv4 subnet-level mtu:%s provided.",
                iface["name"],
                device_mtu,
                ipv4_mtu,
            )

        # Parse type-specific properties
        for nm_prop, key in _prop_map[if_type].items():
            if key not in iface:
                continue
            if iface[key] is None:
                continue
            if isinstance(iface[key], bool):
                self.config[if_type][nm_prop] = (
                    "true" if iface[key] else "false"
                )
            else:
                self.config[if_type][nm_prop] = str(iface[key])

        # These ones need special treatment
        if if_type == "ethernet":
            if iface["wakeonlan"] is True:
                # NM_SETTING_WIRED_WAKE_ON_LAN_MAGIC
                self.config["ethernet"]["wake-on-lan"] = str(0x40)
            if ipv4_mtu is not None:
                self.config["ethernet"]["mtu"] = str(ipv4_mtu)
            if iface["mac_address"] is not None:
                self.config["ethernet"]["mac-address"] = self.mac_addr(
                    iface["mac_address"]
                )
        if if_type == "vlan" and "vlan-raw-device" in iface:
            self.config["vlan"]["parent"] = renderer.con_ref(
                iface["vlan-raw-device"]
            )
        if if_type == "bridge":
            # Bridge is ass-backwards compared to bond
            for port in iface["bridge_ports"]:
                port = renderer.get_conn(port)
                port._set_default("connection", "slave-type", "bridge")
                port._set_default("connection", "master", self.con_uuid())
            if iface["mac_address"] is not None:
                self.config["bridge"]["mac-address"] = self.mac_addr(
                    iface["mac_address"]
                )
        if if_type == "infiniband" and ipv4_mtu is not None:
            self.config["infiniband"]["transport-mode"] = "datagram"
            self.config["infiniband"]["mtu"] = str(ipv4_mtu)
            if iface["mac_address"] is not None:
                self.config["infiniband"]["mac-address"] = self.mac_addr(
                    iface["mac_address"]
                )

        # Finish up
        if if_type == "bridge" or not self.config.has_option(
            if_type, "mac-address"
        ):
            self.config["connection"]["interface-name"] = iface["name"]

    def dump(self):
        """
        Stringify.
        """

        buf = io.StringIO()
        self.config.write(buf, space_around_delimiters=False)
        header = "# Generated by cloud-init. Changes will be lost.\n\n"
        return header + buf.getvalue()


class Renderer(renderer.Renderer):
    """Renders network information in a NetworkManager keyfile format."""

    def __init__(self, config=None):
        self.connections = {}

    def get_conn(self, con_id):
        return self.connections[con_id]

    def con_ref(self, con_id):
        if con_id in self.connections:
            return self.connections[con_id].con_uuid()
        else:
            # Well, what can we do...
            return con_id

    def render_network_state(
        self,
        network_state: NetworkState,
        templates: Optional[dict] = None,
        target=None,
    ) -> None:
        # First pass makes sure there's NMConnections for all known
        # interfaces that have UUIDs that can be linked to from related
        # interfaces
        for iface in network_state.iter_interfaces():
            self.connections[iface["name"]] = NMConnection(iface["name"])

        # Now render the actual interface configuration
        for iface in network_state.iter_interfaces():
            conn = self.connections[iface["name"]]
            conn.render_interface(iface, self)

        # And finally write the files
        for con_id, conn in self.connections.items():
            if not conn.valid():
                continue
            name = conn_filename(con_id, target)
            util.write_file(name, conn.dump(), 0o600)


def conn_filename(con_id, target=None):
    target_con_dir = subp.target_path(target, NM_RUN_DIR)
    con_file = f"cloud-init-{con_id}.nmconnection"
    return f"{target_con_dir}/system-connections/{con_file}"


def available(target=None):
    # TODO: Move `uses_systemd` to a more appropriate location
    # It is imported here to avoid circular import
    from cloudinit.distros import uses_systemd

    config_present = os.path.isfile(subp.target_path(target, path=NM_CFG_FILE))
    nmcli_present = subp.which("nmcli", target=target)
    service_active = True
    if uses_systemd():
        try:
            subp.subp(["systemctl", "is-enabled", "NetworkManager.service"])
        except subp.ProcessExecutionError:
            service_active = False

    return config_present and bool(nmcli_present) and service_active


# vi: ts=4 expandtab
