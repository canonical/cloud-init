# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2016 VMware INC.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re

from cloudinit import util

logger = logging.getLogger(__name__)


class NicConfigurator(object):
    def __init__(self, nics):
        """
        Initialize the Nic Configurator
        @param nics (list) an array of nics to configure
        """
        self.nics = nics
        self.mac2Name = {}
        self.ipv4PrimaryGateway = None
        self.ipv6PrimaryGateway = None
        self.find_devices()
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
        (output, err) = util.subp(cmd)
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
        Return the lines needed to configure a nic
        @return (str list): the string list to configure the nic
        @param nic (NicBase): the nic to configure
        """
        lines = []
        name = self.mac2Name.get(nic.mac.lower())
        if not name:
            raise ValueError('No known device has MACADDR: %s' % nic.mac)

        if nic.onboot:
            lines.append('auto %s' % name)

        # Customize IPv4
        lines.extend(self.gen_ipv4(name, nic))

        # Customize IPv6
        lines.extend(self.gen_ipv6(name, nic))

        lines.append('')

        return lines

    def gen_ipv4(self, name, nic):
        """
        Return the lines needed to configure the IPv4 setting of a nic
        @return (str list): the string list to configure the gateways
        @param name (str): name of the nic
        @param nic (NicBase): the nic to configure
        """
        lines = []

        bootproto = nic.bootProto.lower()
        if nic.ipv4_mode.lower() == 'disabled':
            bootproto = 'manual'
        lines.append('iface %s inet %s' % (name, bootproto))

        if bootproto != 'static':
            return lines

        # Static Ipv4
        v4 = nic.staticIpv4
        if v4.ip:
            lines.append('    address %s' % v4.ip)
        if v4.netmask:
            lines.append('    netmask %s' % v4.netmask)

        # Add the primary gateway
        if nic.primary and v4.gateways:
            self.ipv4PrimaryGateway = v4.gateways[0]
            lines.append('    gateway %s metric 0' % self.ipv4PrimaryGateway)
            return lines

        # Add routes if there is no primary nic
        if not self._primaryNic:
            lines.extend(self.gen_ipv4_route(nic, v4.gateways))

        return lines

    def gen_ipv4_route(self, nic, gateways):
        """
        Return the lines needed to configure additional Ipv4 route
        @return (str list): the string list to configure the gateways
        @param nic (NicBase): the nic to configure
        @param gateways (str list): the list of gateways
        """
        lines = []

        for gateway in gateways:
            lines.append('    up route add default gw %s metric 10000' %
                         gateway)

        return lines

    def gen_ipv6(self, name, nic):
        """
        Return the lines needed to configure the gateways for a nic
        @return (str list): the string list to configure the gateways
        @param name (str): name of the nic
        @param nic (NicBase): the nic to configure
        """
        lines = []

        if not nic.staticIpv6:
            return lines

        # Static Ipv6
        addrs = nic.staticIpv6
        lines.append('iface %s inet6 static' % name)
        lines.append('    address %s' % addrs[0].ip)
        lines.append('    netmask %s' % addrs[0].netmask)

        for addr in addrs[1:]:
            lines.append('    up ifconfig %s inet6 add %s/%s' % (name, addr.ip,
                                                                 addr.netmask))
        # Add the primary gateway
        if nic.primary:
            for addr in addrs:
                if addr.gateway:
                    self.ipv6PrimaryGateway = addr.gateway
                    lines.append('    gateway %s' % self.ipv6PrimaryGateway)
                    return lines

        # Add routes if there is no primary nic
        if not self._primaryNic:
            lines.extend(self._genIpv6Route(name, nic, addrs))

        return lines

    def _genIpv6Route(self, name, nic, addrs):
        lines = []

        for addr in addrs:
            lines.append('    up route -A inet6 add default gw '
                         '%s metric 10000' % addr.gateway)

        return lines

    def generate(self):
        """Return the lines that is needed to configure the nics"""
        lines = []
        lines.append('iface lo inet loopback')
        lines.append('auto lo')
        lines.append('')

        for nic in self.nics:
            lines.extend(self.gen_one_nic(nic))

        return lines

    def clear_dhcp(self):
        logger.info('Clearing DHCP leases')

        # Ignore the return code 1.
        util.subp(["pkill", "dhclient"], rcs=[0, 1])
        util.subp(["rm", "-f", "/var/lib/dhcp/*"])

    def if_down_up(self):
        names = []
        for nic in self.nics:
            name = self.mac2Name.get(nic.mac.lower())
            names.append(name)

        for name in names:
            logger.info('Bring down interface %s' % name)
            util.subp(["ifdown", "%s" % name])

        self.clear_dhcp()

        for name in names:
            logger.info('Bring up interface %s' % name)
            util.subp(["ifup", "%s" % name])

    def configure(self):
        """
        Configure the /etc/network/intefaces
        Make a back up of the original
        """
        containingDir = '/etc/network'

        interfaceFile = os.path.join(containingDir, 'interfaces')
        originalFile = os.path.join(containingDir,
                                    'interfaces.before_vmware_customization')

        if not os.path.exists(originalFile) and os.path.exists(interfaceFile):
            os.rename(interfaceFile, originalFile)

        lines = self.generate()
        with open(interfaceFile, 'w') as fp:
            for line in lines:
                fp.write('%s\n' % line)

        self.if_down_up()

# vi: ts=4 expandtab
