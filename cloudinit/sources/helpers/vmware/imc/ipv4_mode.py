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


class Ipv4ModeEnum(object):
    """
    The IPv4 configuration mode which directly represents the user's goal.

    This mode effectively acts as a contract of the in-guest customization
    engine. It must be set based on what the user has requested and should
    not be changed by those layers. It's up to the in-guest engine to
    interpret and materialize the user's request.
    """

    # The legacy mode which only allows dhcp/static based on whether IPv4
    # addresses list is empty or not
    IPV4_MODE_BACKWARDS_COMPATIBLE = 'BACKWARDS_COMPATIBLE'

    # IPv4 must use static address. Reserved for future use
    IPV4_MODE_STATIC = 'STATIC'

    # IPv4 must use DHCPv4. Reserved for future use
    IPV4_MODE_DHCP = 'DHCP'

    # IPv4 must be disabled
    IPV4_MODE_DISABLED = 'DISABLED'

    # IPv4 settings should be left untouched. Reserved for future use
    IPV4_MODE_AS_IS = 'AS_IS'
