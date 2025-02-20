# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2006-2024 Broadcom. All Rights Reserved.
# Broadcom Confidential. The term "Broadcom" refers to Broadcom Inc.
# and/or its subsidiaries.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#         Pengpeng Sun <pengpeng.sun@broadcom.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import ipaddress
import logging
import os
import re

from cloudinit import net, subp, util
from cloudinit.net.network_state import (
    ipv4_mask_to_net_prefix,
    ipv6_mask_to_net_prefix,
)

logger = logging.getLogger(__name__)


class NicConfigurator:
    def __init__(
        self, nics, name_servers, dns_suffixes, use_system_devices=True
    ):
        """
        Initialize the Nic Configurator
        @param nics (list) an array of nics to configure
        @param use_system_devices (Bool) Get the MAC names from the system
        if this is True. If False, then mac names will be retrieved from
         the specified nics.
        """
        self.nics = nics
        self.name_servers = name_servers
        self.dns_suffixes = dns_suffixes
        self.mac2Name = {}

        if use_system_devices:
            self.find_devices()
        else:
            for nic in self.nics:
                self.mac2Name[nic.mac.lower()] = nic.name

        self._primaryNic = self.get_primary_nic()

    def get_primary_nic(self):
        """
        Retrieve the primary nic if it exists
        @return (NicBase): the primary nic if exists, None otherwise
        """
        primary_nics = [nic for nic in self.nics if nic.primary]
        if not primary_nics:
            return None
        elif len(primary_nics) > 1:
            raise RuntimeError(
                "There can only be one primary nic",
                [nic.mac for nic in primary_nics],
            )
        else:
            return primary_nics[0]

    def find_devices(self):
        """
        Create the mac2Name dictionary
        The mac address(es) are in the lower case
        """
        cmd = ["ip", "addr", "show"]
        output, _err = subp.subp(cmd)
        sections = re.split(r"\n\d+: ", "\n" + output)[1:]

        macPat = r"link/ether (([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2}))"
        for section in sections:
            match = re.search(macPat, section)
            if not match:  # Only keep info about nics
                continue
            mac = match.group(1).lower()
            name = section.split(":", 1)[0]
            self.mac2Name[mac] = name

    def gen_one_nic_v2(self, nic):
        """
        Return the config dict needed to configure a nic
        @return (dict): the config dict to configure the nic
        @param nic (NicBase): the nic to configure
        """
        mac = nic.mac.lower()
        name = self.mac2Name.get(mac)
        if not name:
            raise ValueError("No known device has MACADDR: %s" % nic.mac)

        nic_config_dict = {}
        generators = [
            self.gen_match(mac),
            self.gen_set_name(name),
            self.gen_wakeonlan(nic),
            self.gen_dhcp4(nic),
            self.gen_dhcp6(nic),
            self.gen_addresses(nic),
            self.gen_routes(nic),
            self.gen_nameservers(),
        ]
        for value in generators:
            if value:
                nic_config_dict.update(value)

        return {name: nic_config_dict}

    def gen_match(self, mac):
        return {"match": {"macaddress": mac}}

    def gen_set_name(self, name):
        return {"set-name": name}

    def gen_wakeonlan(self, nic):
        return {"wakeonlan": nic.onboot}

    def gen_dhcp4(self, nic):
        dhcp4 = {}
        bootproto = nic.bootProto.lower()
        if nic.ipv4_mode.lower() == "disabled":
            bootproto = "manual"
        if bootproto != "static":
            dhcp4.update({"dhcp4": True})
            # dhcp4-overrides
            if self.name_servers or self.dns_suffixes:
                dhcp4.update({"dhcp4-overrides": {"use-dns": False}})
        else:
            dhcp4.update({"dhcp4": False})
        return dhcp4

    def gen_dhcp6(self, nic):
        dhcp6 = {}
        if nic.staticIpv6:
            dhcp6.update({"dhcp6": False})
        # TODO: nic shall explicitly tell it's DHCP6
        # TODO: set dhcp6-overrides
        return dhcp6

    def gen_addresses(self, nic):
        address_list = []
        v4_cidr = 32

        # Static Ipv4
        v4_addrs = nic.staticIpv4
        if v4_addrs:
            v4 = v4_addrs[0]
            if v4.netmask:
                v4_cidr = ipv4_mask_to_net_prefix(v4.netmask)
            if v4.ip:
                address_list.append(f"{v4.ip}/{v4_cidr}")
        # Static Ipv6
        v6_addrs = nic.staticIpv6
        if v6_addrs:
            for v6 in v6_addrs:
                v6_cidr = ipv6_mask_to_net_prefix(v6.netmask)
                address_list.append(f"{v6.ip}/{v6_cidr}")

        if address_list:
            return {"addresses": address_list}
        else:
            return {}

    def gen_routes(self, nic):
        route_list = []
        v4_cidr = 32

        # Ipv4 routes
        v4_addrs = nic.staticIpv4
        if v4_addrs:
            v4 = v4_addrs[0]
            # Add the ipv4 default route
            if nic.primary and v4.gateways:
                route_list.append({"to": "0.0.0.0/0", "via": v4.gateways[0]})
            # Add ipv4 static routes if there is no primary nic
            if not self._primaryNic and v4.gateways:
                if v4.netmask:
                    v4_cidr = ipv4_mask_to_net_prefix(v4.netmask)
                for gateway in v4.gateways:
                    v4_subnet = ipaddress.IPv4Network(
                        f"{gateway}/{v4_cidr}", strict=False
                    )
                    route_list.append({"to": f"{v4_subnet}", "via": gateway})
        # Ipv6 routes
        v6_addrs = nic.staticIpv6
        if v6_addrs:
            for v6 in v6_addrs:
                v6_cidr = ipv6_mask_to_net_prefix(v6.netmask)
                # Add the ipv6 default route
                if nic.primary and v6.gateway:
                    route_list.append({"to": "::/0", "via": v6.gateway})
                # Add ipv6 static routes if there is no primary nic
                if not self._primaryNic and v6.gateway:
                    v6_subnet = ipaddress.IPv6Network(
                        f"{v6.gateway}/{v6_cidr}", strict=False
                    )
                    route_list.append(
                        {"to": f"{v6_subnet}", "via": v6.gateway}
                    )

        if route_list:
            return {"routes": route_list}
        else:
            return {}

    def gen_nameservers(self):
        nameservers_dict = {}
        search_list = []
        addresses_list = []
        if self.dns_suffixes:
            for dns_suffix in self.dns_suffixes:
                search_list.append(dns_suffix)
        if self.name_servers:
            for name_server in self.name_servers:
                addresses_list.append(name_server)
        if search_list:
            nameservers_dict.update({"search": search_list})
        if addresses_list:
            nameservers_dict.update({"addresses": addresses_list})

        if nameservers_dict:
            return {"nameservers": nameservers_dict}
        else:
            return {}

    def generate(self, configure=False, osfamily=None):
        """Return the config elements that are needed to configure the nics"""
        if configure:
            logger.info("Configuring the interfaces file")
            self.configure(osfamily)

        ethernets_dict = {}

        for nic in self.nics:
            ethernets_dict.update(self.gen_one_nic_v2(nic))

        return ethernets_dict

    def clear_dhcp(self):
        logger.info("Clearing DHCP leases")
        net.dhcp.IscDhclient.clear_leases()

    def configure(self, osfamily=None):
        """
        Configure the /etc/network/interfaces
        Make a back up of the original
        """

        if not osfamily or osfamily != "debian":
            logger.info("Debian OS not detected. Skipping the configure step")
            return

        containingDir = "/etc/network"

        interfaceFile = os.path.join(containingDir, "interfaces")
        originalFile = os.path.join(
            containingDir, "interfaces.before_vmware_customization"
        )

        if not os.path.exists(originalFile) and os.path.exists(interfaceFile):
            os.rename(interfaceFile, originalFile)

        lines = [
            "# DO NOT EDIT THIS FILE BY HAND --"
            " AUTOMATICALLY GENERATED BY cloud-init",
            "source /etc/network/interfaces.d/*",
            "source-directory /etc/network/interfaces.d",
        ]

        util.write_file(interfaceFile, content="\n".join(lines))

        self.clear_dhcp()
