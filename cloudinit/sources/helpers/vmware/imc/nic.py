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

from .boot_proto import BootProtoEnum
from .nic_base import NicBase, StaticIpv4Base, StaticIpv6Base


class Nic(NicBase):
    """
    Holds the information about each NIC specified
    in the customization specification file
    """

    def __init__(self, name, configFile):
        self._name = name
        self._configFile = configFile

    def _get(self, what):
        return self._configFile.get(self.name + '|' + what, None)

    def _get_count_with_prefix(self, prefix):
        return self._configFile.get_count_with_prefix(self.name + prefix)

    @property
    def name(self):
        return self._name

    @property
    def mac(self):
        return self._get('MACADDR').lower()

    @property
    def primary(self):
        value = self._get('PRIMARY')
        if value:
           value = value.lower()
           return value == 'yes' or value == 'true'
        else:
           return False

    @property
    def onboot(self):
        value = self._get('ONBOOT')
        if value:
           value = value.lower()
           return value == 'yes' or value == 'true'
        else:
           return False

    @property
    def bootProto(self):
        value = self._get('BOOTPROTO')
        if value:
           return value.lower()
        else:
           return ""

    @property
    def ipv4_mode(self):
        value = self._get('IPv4_MODE')
        if value:
           return value.lower()
        else:
           return ""

    @property
    def staticIpv4(self):
        """
        Checks the BOOTPROTO property and returns StaticIPv4Addr
        configuration object if STATIC configuration is set.
        """
        if self.bootProto == BootProtoEnum.STATIC:
            return [StaticIpv4Addr(self)]
        else:
            return None

    @property
    def staticIpv6(self):
        cnt = self._get_count_with_prefix('|IPv6ADDR|')

        if not cnt:
            return None

        result = []
        for index in range(1, cnt + 1):
            result.append(StaticIpv6Addr(self, index))

        return result


class StaticIpv4Addr(StaticIpv4Base):
    """Static IPV4  Setting."""

    def __init__(self, nic):
        self._nic = nic

    @property
    def ip(self):
        return self._nic._get('IPADDR')

    @property
    def netmask(self):
        return self._nic._get('NETMASK')

    @property
    def gateways(self):
        value = self._nic._get('GATEWAY')
        if value:
            return [x.strip() for x in value.split(',')]
        else:
            return None


class StaticIpv6Addr(StaticIpv6Base):
    """Static IPV6 Address."""

    def __init__(self, nic, index):
        self._nic = nic
        self._index = index

    @property
    def ip(self):
        return self._nic._get('IPv6ADDR|' + str(self._index))

    @property
    def netmask(self):
        return self._nic._get('IPv6NETMASK|' + str(self._index))

    @property
    def gateway(self):
        return self._nic._get('IPv6GATEWAY|' + str(self._index))
