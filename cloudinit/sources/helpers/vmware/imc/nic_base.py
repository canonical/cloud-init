# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class NicBase(object):
    """
    Define what are expected of each nic.
    The following properties should be provided in an implementation class.
    """

    @property
    def mac(self):
        """
        Retrieves the mac address of the nic
        @return (str) : the MACADDR setting
        """
        raise NotImplementedError('MACADDR')

    @property
    def primary(self):
        """
        Retrieves whether the nic is the primary nic
        Indicates whether NIC will be used to define the default gateway.
        If none of the NICs is configured to be primary, default gateway won't
        be set.
        @return (bool): the PRIMARY setting
        """
        raise NotImplementedError('PRIMARY')

    @property
    def onboot(self):
        """
        Retrieves whether the nic should be up at the boot time
        @return (bool) : the ONBOOT setting
        """
        raise NotImplementedError('ONBOOT')

    @property
    def bootProto(self):
        """
        Retrieves the boot protocol of the nic
        @return (str): the BOOTPROTO setting, valid values: dhcp and static.
        """
        raise NotImplementedError('BOOTPROTO')

    @property
    def ipv4_mode(self):
        """
        Retrieves the IPv4_MODE
        @return (str): the IPv4_MODE setting, valid values:
        backwards_compatible, static, dhcp, disabled, as_is
        """
        raise NotImplementedError('IPv4_MODE')

    @property
    def staticIpv4(self):
        """
        Retrieves the static IPv4 configuration of the nic
        @return (StaticIpv4Base list): the static ipv4 setting
        """
        raise NotImplementedError('Static IPv4')

    @property
    def staticIpv6(self):
        """
        Retrieves the IPv6 configuration of the nic
        @return (StaticIpv6Base list): the static ipv6 setting
        """
        raise NotImplementedError('Static Ipv6')

    def validate(self):
        """
        Validate the object
        For example, the staticIpv4 property is required and should not be
        empty when ipv4Mode is STATIC
        """
        raise NotImplementedError('Check constraints on properties')


class StaticIpv4Base(object):
    """
    Define what are expected of a static IPv4 setting
    The following properties should be provided in an implementation class.
    """

    @property
    def ip(self):
        """
        Retrieves the Ipv4 address
        @return (str): the IPADDR setting
        """
        raise NotImplementedError('Ipv4 Address')

    @property
    def netmask(self):
        """
        Retrieves the Ipv4 NETMASK setting
        @return (str): the NETMASK setting
        """
        raise NotImplementedError('Ipv4 NETMASK')

    @property
    def gateways(self):
        """
        Retrieves the gateways on this Ipv4 subnet
        @return (str list): the GATEWAY setting
        """
        raise NotImplementedError('Ipv4 GATEWAY')


class StaticIpv6Base(object):
    """Define what are expected of a static IPv6 setting
    The following properties should be provided in an implementation class.
    """

    @property
    def ip(self):
        """
        Retrieves the Ipv6 address
        @return (str): the IPv6ADDR setting
        """
        raise NotImplementedError('Ipv6 Address')

    @property
    def netmask(self):
        """
        Retrieves the Ipv6 NETMASK setting
        @return (str): the IPv6NETMASK setting
        """
        raise NotImplementedError('Ipv6 NETMASK')

    @property
    def gateway(self):
        """
        Retrieves the Ipv6 GATEWAY setting
        @return (str): the IPv6GATEWAY setting
        """
        raise NotImplementedError('Ipv6 GATEWAY')

# vi: ts=4 expandtab
