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

from .nic import Nic


class Config(object):
    """
    Stores the Contents specified in the Customization
    Specification file.
    """

    DNS = 'DNS|NAMESERVER|'
    SUFFIX = 'DNS|SUFFIX|'
    PASS = 'PASSWORD|-PASS'
    TIMEZONE = 'DATETIME|TIMEZONE'
    UTC = 'DATETIME|UTC'
    HOSTNAME = 'NETWORK|HOSTNAME'
    DOMAINNAME = 'NETWORK|DOMAINNAME'

    def __init__(self, configFile):
        self._configFile = configFile

    @property
    def host_name(self):
        """Return the hostname."""
        return self._configFile.get(Config.HOSTNAME, None)

    @property
    def domain_name(self):
        """Return the domain name."""
        return self._configFile.get(Config.DOMAINNAME, None)

    @property
    def timezone(self):
        """Return the timezone."""
        return self._configFile.get(Config.TIMEZONE, None)

    @property
    def utc(self):
        """Retrieves whether to set time to UTC or Local."""
        return self._configFile.get(Config.UTC, None)

    @property
    def admin_password(self):
        """Return the root password to be set."""
        return self._configFile.get(Config.PASS, None)

    @property
    def name_servers(self):
        """Return the list of DNS servers."""
        res = []
        cnt = self._configFile.get_count_with_prefix(Config.DNS)
        for i in range(1, cnt + 1):
            key = Config.DNS + str(i)
            res.append(self._configFile[key])

        return res

    @property
    def dns_suffixes(self):
        """Return the list of DNS Suffixes."""
        res = []
        cnt = self._configFile.get_count_with_prefix(Config.SUFFIX)
        for i in range(1, cnt + 1):
            key = Config.SUFFIX + str(i)
            res.append(self._configFile[key])

        return res

    @property
    def nics(self):
        """Return the list of associated NICs."""
        res = []
        nics = self._configFile['NIC-CONFIG|NICS']
        for nic in nics.split(','):
            res.append(Nic(nic, self._configFile))

        return res
