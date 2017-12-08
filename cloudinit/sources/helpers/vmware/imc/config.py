# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


from .nic import Nic


class Config(object):
    """
    Stores the Contents specified in the Customization
    Specification file.
    """

    CUSTOM_SCRIPT = 'CUSTOM-SCRIPT|SCRIPT-NAME'
    DNS = 'DNS|NAMESERVER|'
    DOMAINNAME = 'NETWORK|DOMAINNAME'
    HOSTNAME = 'NETWORK|HOSTNAME'
    MARKERID = 'MISC|MARKER-ID'
    PASS = 'PASSWORD|-PASS'
    RESETPASS = 'PASSWORD|RESET'
    SUFFIX = 'DNS|SUFFIX|'
    TIMEZONE = 'DATETIME|TIMEZONE'
    UTC = 'DATETIME|UTC'

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

    @property
    def reset_password(self):
        """Retreives if the root password needs to be reset."""
        resetPass = self._configFile.get(Config.RESETPASS, 'no')
        resetPass = resetPass.lower()
        if resetPass not in ('yes', 'no'):
            raise ValueError('ResetPassword value should be yes/no')
        return resetPass == 'yes'

    @property
    def marker_id(self):
        """Returns marker id."""
        return self._configFile.get(Config.MARKERID, None)

    @property
    def custom_script_name(self):
        """Return the name of custom (pre/post) script."""
        return self._configFile.get(Config.CUSTOM_SCRIPT, None)
# vi: ts=4 expandtab
