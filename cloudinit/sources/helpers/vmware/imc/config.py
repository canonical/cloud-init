from cloudinit.sources.helpers.vmware.imc.nic import Nic


class Config:
    DNS = 'DNS|NAMESERVER|'
    SUFFIX = 'DNS|SUFFIX|'
    PASS = 'PASSWORD|-PASS'
    TIMEZONE = 'DATETIME|TIMEZONE'
    UTC = 'DATETIME|UTC'
    HOSTNAME = 'NETWORK|HOSTNAME'
    OMAINNAME = 'NETWORK|DOMAINNAME'

    def __init__(self, configFile):
        self._configFile = configFile

    # Retrieves hostname.
    #
    # Args:
    #   None
    # Results:
    #   string: hostname
    # Throws:
    #   None
    @property
    def hostName(self):
        return self._configFile.get(Config.HOSTNAME, None)

    # Retrieves domainName.
    #
    # Args:
    #   None
    # Results:
    #   string: domainName
    # Throws:
    #   None
    @property
    def domainName(self):
        return self._configFile.get(Config.DOMAINNAME, None)

    # Retrieves timezone.
    #
    # Args:
    #   None
    # Results:
    #   string: timezone
    # Throws:
    #   None
    @property
    def timeZone(self):
        return self._configFile.get(Config.TIMEZONE, None)

    # Retrieves whether to set time to UTC or Local.
    #
    # Args:
    #   None
    # Results:
    #   boolean: True for yes/YES, True for no/NO, otherwise - None
    # Throws:
    #   None
    @property
    def utc(self):
        return self._configFile.get(Config.UTC, None)

    # Retrieves root password to be set.
    #
    # Args:
    #   None
    # Results:
    #   string: base64-encoded root password or None
    # Throws:
    #   None
    @property
    def adminPassword(self):
        return self._configFile.get(Config.PASS, None)

    # Retrieves DNS Servers.
    #
    # Args:
    #   None
    # Results:
    #   integer: count or 0
    # Throws:
    #   None
    @property
    def nameServers(self):
        res = []
        for i in range(1, self._configFile.getCnt(Config.DNS) + 1):
            key = Config.DNS + str(i)
            res.append(self._configFile[key])

        return res

    # Retrieves DNS Suffixes.
    #
    # Args:
    #   None
    # Results:
    #   integer: count or 0
    # Throws:
    #   None
    @property
    def dnsSuffixes(self):
        res = []
        for i in range(1, self._configFile.getCnt(Config.SUFFIX) + 1):
            key = Config.SUFFIX + str(i)
            res.append(self._configFile[key])

        return res

    # Retrieves NICs.
    #
    # Args:
    #   None
    # Results:
    #   integer: count
    # Throws:
    #   None
    @property
    def nics(self):
        res = []
        nics = self._configFile['NIC-CONFIG|NICS']
        for nic in nics.split(','):
            res.append(Nic(nic, self._configFile))

        return res
