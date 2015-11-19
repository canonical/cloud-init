from cloudinit.sources.helpers.vmware.imc.boot_proto import BootProto


class Nic:
    def __init__(self, name, configFile):
        self._name = name
        self._configFile = configFile

    def _get(self, what):
        return self._configFile.get(self.name + what, None)

    def _getCnt(self, prefix):
        return self._configFile.getCnt(self.name + prefix)

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
        # TODO implement NONE
        if self.bootProto == BootProto.STATIC:
            return StaticIpv4Conf(self)

        return DhcpIpv4Conf(self)

    @property
    def ipv6(self):
        # TODO implement NONE
        cnt = self._getCnt("|IPv6ADDR|")

        if cnt != 0:
            return StaticIpv6Conf(self)

        return DhcpIpv6Conf(self)


class DhcpIpv4Conf:
    def __init__(self, nic):
        self._nic = nic


class StaticIpv4Addr:
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
    @property
    def addrs(self):
        return [StaticIpv4Addr(self._nic)]


class DhcpIpv6Conf:
    def __init__(self, nic):
        self._nic = nic


class StaticIpv6Addr:
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
    @property
    def addrs(self):
        cnt = self._nic._getCnt("|IPv6ADDR|")

        res = []

        for i in range(1, cnt + 1):
            res.append(StaticIpv6Addr(self._nic, i))

        return res
