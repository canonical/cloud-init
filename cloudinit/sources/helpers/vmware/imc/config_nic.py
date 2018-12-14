# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2016 VMware INC.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re

from cloudinit.net.network_state import mask_to_net_prefix
from cloudinit import util

logger = logging.getLogger(__name__)


def gen_subnet(ip, netmask):
    """
    Return the subnet for a given ip address and a netmask
    @return (str): the subnet
    @param ip: ip address
    @param netmask: netmask
    """
    ip_array = ip.split(".")
    mask_array = netmask.split(".")
    result = []
    for index in list(range(4)):
        result.append(int(ip_array[index]) & int(mask_array[index]))

    return ".".join([str(x) for x in result])


class NicConfigurator(object):
    def __init__(self, nics, use_system_devices=True):
        """
        Initialize the Nic Configurator
        @param nics (list) an array of nics to configure
        @param use_system_devices (Bool) Get the MAC names from the system
        if this is True. If False, then mac names will be retrieved from
         the specified nics.
        """
        self.nics = nics
        self.mac2Name = {}
        self.ipv4PrimaryGateway = None
        self.ipv6PrimaryGateway = None

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
            raise Exception('There can only be one primary nic',
                            [nic.mac for nic in primary_nics])
        else:
            return primary_nics[0]

    def find_devices(self):
        """
        Create the mac2Name dictionary
        The mac address(es) are in the lower case
        """
        cmd = ['ip', 'addr', 'show']
        output, _err = util.subp(cmd)
        sections = re.split(r'\n\d+: ', '\n' + output)[1:]

        macPat = r'link/ether (([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2}))'
        for section in sections:
            match = re.search(macPat, section)
            if not match:  # Only keep info about nics
                continue
            mac = match.group(1).lower()
            name = section.split(':', 1)[0]
            self.mac2Name[mac] = name

    def gen_one_nic(self, nic):
        """
        Return the config list needed to configure a nic
        @return (list): the subnets and routes list to configure the nic
        @param nic (NicBase): the nic to configure
        """
        mac = nic.mac.lower()
        name = self.mac2Name.get(mac)
        if not name:
            raise ValueError('No known device has MACADDR: %s' % nic.mac)

        nics_cfg_list = []

        cfg = {'type': 'physical', 'name': name, 'mac_address': mac}

        subnet_list = []
        route_list = []

        # Customize IPv4
        (subnets, routes) = self.gen_ipv4(name, nic)
        subnet_list.extend(subnets)
        route_list.extend(routes)

        # Customize IPv6
        (subnets, routes) = self.gen_ipv6(name, nic)
        subnet_list.extend(subnets)
        route_list.extend(routes)

        cfg.update({'subnets': subnet_list})

        nics_cfg_list.append(cfg)
        if route_list:
            nics_cfg_list.extend(route_list)

        return nics_cfg_list

    def gen_ipv4(self, name, nic):
        """
        Return the set of subnets and routes needed to configure the
        IPv4 settings of a nic
        @return (set): the set of subnet and routes to configure the gateways
        @param name (str): subnet and route list for the nic
        @param nic (NicBase): the nic to configure
        """

        subnet = {}
        route_list = []

        if nic.onboot:
            subnet.update({'control': 'auto'})

        bootproto = nic.bootProto.lower()
        if nic.ipv4_mode.lower() == 'disabled':
            bootproto = 'manual'

        if bootproto != 'static':
            subnet.update({'type': 'dhcp'})
            return ([subnet], route_list)
        else:
            subnet.update({'type': 'static'})

        # Static Ipv4
        addrs = nic.staticIpv4
        if not addrs:
            return ([subnet], route_list)

        v4 = addrs[0]
        if v4.ip:
            subnet.update({'address': v4.ip})
        if v4.netmask:
            subnet.update({'netmask': v4.netmask})

        # Add the primary gateway
        if nic.primary and v4.gateways:
            self.ipv4PrimaryGateway = v4.gateways[0]
            subnet.update({'gateway': self.ipv4PrimaryGateway})
            return ([subnet], route_list)

        # Add routes if there is no primary nic
        if not self._primaryNic and v4.gateways:
            subnet.update(
                {'routes': self.gen_ipv4_route(nic, v4.gateways, v4.netmask)})

        return ([subnet], route_list)

    def gen_ipv4_route(self, nic, gateways, netmask):
        """
        Return the routes list needed to configure additional Ipv4 route
        @return (list): the route list to configure the gateways
        @param nic (NicBase): the nic to configure
        @param gateways (str list): the list of gateways
        """
        route_list = []

        cidr = mask_to_net_prefix(netmask)

        for gateway in gateways:
            destination = "%s/%d" % (gen_subnet(gateway, netmask), cidr)
            route_list.append({'destination': destination,
                               'type': 'route',
                               'gateway': gateway,
                               'metric': 10000})

        return route_list

    def gen_ipv6(self, name, nic):
        """
        Return the set of subnets and routes needed to configure the
        gateways for a nic
        @return (set): the set of subnets and routes to configure the gateways
        @param name (str): name of the nic
        @param nic (NicBase): the nic to configure
        """

        if not nic.staticIpv6:
            return ([], [])

        subnet_list = []
        # Static Ipv6
        addrs = nic.staticIpv6

        for addr in addrs:
            subnet = {'type': 'static6',
                      'address': addr.ip,
                      'netmask': addr.netmask}
            subnet_list.append(subnet)

        # TODO: Add the primary gateway

        route_list = []
        # TODO: Add routes if there is no primary nic
        # if not self._primaryNic:
        #    route_list.extend(self._genIpv6Route(name, nic, addrs))

        return (subnet_list, route_list)

    def _genIpv6Route(self, name, nic, addrs):
        route_list = []

        for addr in addrs:
            route_list.append({'type': 'route',
                               'gateway': addr.gateway,
                               'metric': 10000})

        return route_list

    def generate(self, configure=False, osfamily=None):
        """Return the config elements that are needed to configure the nics"""
        if configure:
            logger.info("Configuring the interfaces file")
            self.configure(osfamily)

        nics_cfg_list = []

        for nic in self.nics:
            nics_cfg_list.extend(self.gen_one_nic(nic))

        return nics_cfg_list

    def clear_dhcp(self):
        logger.info('Clearing DHCP leases')

        # Ignore the return code 1.
        util.subp(["pkill", "dhclient"], rcs=[0, 1])
        util.subp(["rm", "-f", "/var/lib/dhcp/*"])

    def configure(self, osfamily=None):
        """
        Configure the /etc/network/interfaces
        Make a back up of the original
        """

        if not osfamily or osfamily != "debian":
            logger.info("Debian OS not detected. Skipping the configure step")
            return

        containingDir = '/etc/network'

        interfaceFile = os.path.join(containingDir, 'interfaces')
        originalFile = os.path.join(containingDir,
                                    'interfaces.before_vmware_customization')

        if not os.path.exists(originalFile) and os.path.exists(interfaceFile):
            os.rename(interfaceFile, originalFile)

        lines = [
            "# DO NOT EDIT THIS FILE BY HAND --"
            " AUTOMATICALLY GENERATED BY cloud-init",
            "source /etc/network/interfaces.d/*.cfg",
        ]

        util.write_file(interfaceFile, content='\n'.join(lines))

        self.clear_dhcp()

# vi: ts=4 expandtab
