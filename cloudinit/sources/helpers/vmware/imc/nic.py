# vi: ts=4 expandtab
#
#    Copyright (C) 2015 Canonical Ltd.
#    Copyright (C) 2015 VMware Inc.
#
#    Author: Sankar Tanguturi <stanguturi@vmware.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from .boot_proto import BootProto


class Nic:
    """
    Holds the information about each NIC specified
    in the customization specification file
    """

    def __init__(self, name, configFile):
        self._name = name
        self._configFile = configFile

    def _get(self, what):
        return self._configFile.get(self.name + what, None)

    def _get_count(self, prefix):
        return self._configFile.get_count(self.name + prefix)

    @property
    def name(self):
        return self._name

    @property
    def mac(self):
        return self._get('|MACADDR').lower()

    @property
    def bootProto(self):
        return self._get('|BOOTPROTO').lower()

    @property
    def ipv4(self):
        """
        Retrieves the DHCP or Static IPv6 configuration
        based on the BOOTPROTO property associated with the NIC
        """
        if self.bootProto == BootProto.STATIC:
            return StaticIpv4Conf(self)

        return DhcpIpv4Conf(self)

    @property
    def ipv6(self):
        cnt = self._get_count("|IPv6ADDR|")

        if cnt != 0:
            return StaticIpv6Conf(self)

        return DhcpIpv6Conf(self)


class DhcpIpv4Conf:
    """DHCP Configuration Setting."""

    def __init__(self, nic):
        self._nic = nic


class StaticIpv4Addr:
    """Static IPV4  Setting."""

    def __init__(self, nic):
        self._nic = nic

    @property
    def ip(self):
        return self._nic._get('|IPADDR')

    @property
    def netmask(self):
        return self._nic._get('|NETMASK')

    @property
    def gateway(self):
        return self._nic._get('|GATEWAY')


class StaticIpv4Conf(DhcpIpv4Conf):
    """Static IPV4 Configuration."""

    @property
    def addrs(self):
        """Return the list of associated IPv4 addresses."""
        return [StaticIpv4Addr(self._nic)]


class DhcpIpv6Conf:
    """DHCP IPV6 Configuration."""

    def __init__(self, nic):
        self._nic = nic


class StaticIpv6Addr:
    """Static IPV6 Address."""

    def __init__(self, nic, index):
        self._nic = nic
        self._index = index

    @property
    def ip(self):
        return self._nic._get("|IPv6ADDR|" + str(self._index))

    @property
    def prefix(self):
        return self._nic._get("|IPv6NETMASK|" + str(self._index))

    @property
    def gateway(self):
        return self._nic._get("|IPv6GATEWAY|" + str(self._index))


class StaticIpv6Conf(DhcpIpv6Conf):
    """Static IPV6 Configuration."""

    @property
    def addrs(self):
        """Return the list Associated IPV6 addresses."""
        cnt = self._nic._get_count("|IPv6ADDR|")

        res = []

        for i in range(1, cnt + 1):
            res.append(StaticIpv6Addr(self._nic, i))

        return res
