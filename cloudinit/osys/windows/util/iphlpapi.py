# Copyright (C) 2015 Canonical Ltd.
# Copyright 2015 Cloudbase Solutions Srl
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Claudiu Popa <cpopa@cloudbasesolutions.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ctypes

from ctypes import windll
from ctypes import wintypes

from cloudinit.osys.windows.util import kernel32
from cloudinit.osys.windows.util import ws2_32

ERROR_INSUFFICIENT_BUFFER = 122

MAX_ADAPTER_NAME_LENGTH = 256
MAX_ADAPTER_DESCRIPTION_LENGTH = 128
MAX_ADAPTER_ADDRESS_LENGTH = 8

# Do not return IPv6 anycast addresses.
GAA_FLAG_SKIP_ANYCAST = 2
GAA_FLAG_SKIP_ANYCAST = 4

IP_ADAPTER_DHCP_ENABLED = 4
IP_ADAPTER_IPV4_ENABLED = 0x80
IP_ADAPTER_IPV6_ENABLED = 0x0100

MAX_DHCPV6_DUID_LENGTH = 130

IF_TYPE_ETHERNET_CSMACD = 6
IF_TYPE_SOFTWARE_LOOPBACK = 24
IF_TYPE_IEEE80211 = 71
IF_TYPE_TUNNEL = 131

IP_ADAPTER_ADDRESSES_SIZE_2003 = 144


class SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [
        ('lpSockaddr', ctypes.POINTER(ws2_32.SOCKADDR)),
        ('iSockaddrLength', wintypes.INT),
    ]


class IP_ADAPTER_ADDRESSES_Struct1(ctypes.Structure):
    _fields_ = [
        ('Length', wintypes.ULONG),
        ('IfIndex', wintypes.DWORD),
    ]


class IP_ADAPTER_ADDRESSES_Union1(ctypes.Union):
    _fields_ = [
        ('Alignment', wintypes.ULARGE_INTEGER),
        ('Struct1', IP_ADAPTER_ADDRESSES_Struct1),
    ]


class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    _fields_ = [
        ('Union1', IP_ADAPTER_ADDRESSES_Union1),
        ('Next', wintypes.LPVOID),
        ('Address', SOCKET_ADDRESS),
        ('PrefixOrigin', wintypes.DWORD),
        ('SuffixOrigin', wintypes.DWORD),
        ('DadState', wintypes.DWORD),
        ('ValidLifetime', wintypes.ULONG),
        ('PreferredLifetime', wintypes.ULONG),
        ('LeaseLifetime', wintypes.ULONG),
    ]


class IP_ADAPTER_DNS_SERVER_ADDRESS_Struct1(ctypes.Structure):
    _fields_ = [
        ('Length', wintypes.ULONG),
        ('Reserved', wintypes.DWORD),
    ]


class IP_ADAPTER_DNS_SERVER_ADDRESS_Union1(ctypes.Union):
    _fields_ = [
        ('Alignment', wintypes.ULARGE_INTEGER),
        ('Struct1', IP_ADAPTER_DNS_SERVER_ADDRESS_Struct1),
    ]


class IP_ADAPTER_DNS_SERVER_ADDRESS(ctypes.Structure):
    _fields_ = [
        ('Union1', IP_ADAPTER_DNS_SERVER_ADDRESS_Union1),
        ('Next', wintypes.LPVOID),
        ('Address', SOCKET_ADDRESS),
    ]


class IP_ADAPTER_PREFIX_Struct1(ctypes.Structure):
    _fields_ = [
        ('Length', wintypes.ULONG),
        ('Flags', wintypes.DWORD),
    ]


class IP_ADAPTER_PREFIX_Union1(ctypes.Union):
    _fields_ = [
        ('Alignment', wintypes.ULARGE_INTEGER),
        ('Struct1', IP_ADAPTER_PREFIX_Struct1),
    ]


class IP_ADAPTER_PREFIX(ctypes.Structure):
    _fields_ = [
        ('Union1', IP_ADAPTER_PREFIX_Union1),
        ('Next', wintypes.LPVOID),
        ('Address', SOCKET_ADDRESS),
        ('PrefixLength', wintypes.ULONG),
    ]


class NET_LUID_LH(ctypes.Union):
    _fields_ = [
        ('Value', wintypes.ULARGE_INTEGER),
        ('Info', wintypes.ULARGE_INTEGER),
    ]


class IP_ADAPTER_ADDRESSES(ctypes.Structure):
    _fields_ = [
        ('Union1', IP_ADAPTER_ADDRESSES_Union1),
        ('Next', wintypes.LPVOID),
        ('AdapterName', ctypes.c_char_p),
        ('FirstUnicastAddress',
         ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
        ('FirstAnycastAddress',
         ctypes.POINTER(IP_ADAPTER_DNS_SERVER_ADDRESS)),
        ('FirstMulticastAddress',
         ctypes.POINTER(IP_ADAPTER_DNS_SERVER_ADDRESS)),
        ('FirstDnsServerAddress',
         ctypes.POINTER(IP_ADAPTER_DNS_SERVER_ADDRESS)),
        ('DnsSuffix', wintypes.LPWSTR),
        ('Description', wintypes.LPWSTR),
        ('FriendlyName', wintypes.LPWSTR),
        ('PhysicalAddress', ctypes.c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
        ('PhysicalAddressLength', wintypes.DWORD),
        ('Flags', wintypes.DWORD),
        ('Mtu', wintypes.DWORD),
        ('IfType', wintypes.DWORD),
        ('OperStatus', wintypes.DWORD),
        ('Ipv6IfIndex', wintypes.DWORD),
        ('ZoneIndices', wintypes.DWORD * 16),
        ('FirstPrefix', ctypes.POINTER(IP_ADAPTER_PREFIX)),
        # kernel >= 6.0
        ('TransmitLinkSpeed', wintypes.ULARGE_INTEGER),
        ('ReceiveLinkSpeed', wintypes.ULARGE_INTEGER),
        ('FirstWinsServerAddress',
         ctypes.POINTER(IP_ADAPTER_DNS_SERVER_ADDRESS)),
        ('FirstGatewayAddress',
         ctypes.POINTER(IP_ADAPTER_DNS_SERVER_ADDRESS)),
        ('Ipv4Metric', wintypes.ULONG),
        ('Ipv6Metric', wintypes.ULONG),
        ('Luid', NET_LUID_LH),
        ('Dhcpv4Server', SOCKET_ADDRESS),
        ('CompartmentId', wintypes.DWORD),
        ('NetworkGuid', kernel32.GUID),
        ('ConnectionType', wintypes.DWORD),
        ('TunnelType', wintypes.DWORD),
        ('Dhcpv6Server', SOCKET_ADDRESS),
        ('Dhcpv6ClientDuid', ctypes.c_ubyte * MAX_DHCPV6_DUID_LENGTH),
        ('Dhcpv6ClientDuidLength', wintypes.ULONG),
        ('Dhcpv6Iaid', wintypes.ULONG),
    ]


class Win32_MIB_IPFORWARDROW(ctypes.Structure):
    _fields_ = [
        ('dwForwardDest', wintypes.DWORD),
        ('dwForwardMask', wintypes.DWORD),
        ('dwForwardPolicy', wintypes.DWORD),
        ('dwForwardNextHop', wintypes.DWORD),
        ('dwForwardIfIndex', wintypes.DWORD),
        ('dwForwardType', wintypes.DWORD),
        ('dwForwardProto', wintypes.DWORD),
        ('dwForwardAge', wintypes.DWORD),
        ('dwForwardNextHopAS', wintypes.DWORD),
        ('dwForwardMetric1', wintypes.DWORD),
        ('dwForwardMetric2', wintypes.DWORD),
        ('dwForwardMetric3', wintypes.DWORD),
        ('dwForwardMetric4', wintypes.DWORD),
        ('dwForwardMetric5', wintypes.DWORD)
    ]


class Win32_MIB_IPFORWARDTABLE(ctypes.Structure):
    _fields_ = [
        ('dwNumEntries', wintypes.DWORD),
        ('table', Win32_MIB_IPFORWARDROW * 1)
    ]


GetAdaptersAddresses = windll.Iphlpapi.GetAdaptersAddresses
GetAdaptersAddresses.argtypes = [
    wintypes.ULONG, wintypes.ULONG, wintypes.LPVOID,
    ctypes.POINTER(IP_ADAPTER_ADDRESSES),
    ctypes.POINTER(wintypes.ULONG)]
GetAdaptersAddresses.restype = wintypes.ULONG

GetIpForwardTable = windll.Iphlpapi.GetIpForwardTable
GetIpForwardTable.argtypes = [
    ctypes.POINTER(Win32_MIB_IPFORWARDTABLE),
    ctypes.POINTER(wintypes.ULONG),
    wintypes.BOOL]
GetIpForwardTable.restype = wintypes.DWORD
