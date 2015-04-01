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

AF_UNSPEC = 0
AF_INET = 2
AF_INET6 = 23

VERSION_2_2 = (2 << 8) + 2


class SOCKADDR(ctypes.Structure):
    _fields_ = [
        ('sa_family', wintypes.USHORT),
        ('sa_data', ctypes.c_char * 14),
    ]


class WSADATA(ctypes.Structure):
    _fields_ = [
        ('opaque_data', wintypes.BYTE * 400),
    ]


WSAGetLastError = windll.Ws2_32.WSAGetLastError
WSAGetLastError.argtypes = []
WSAGetLastError.restype = wintypes.INT

WSAStartup = windll.Ws2_32.WSAStartup
WSAStartup.argtypes = [wintypes.WORD, ctypes.POINTER(WSADATA)]
WSAStartup.restype = wintypes.INT

WSACleanup = windll.Ws2_32.WSACleanup
WSACleanup.argtypes = []
WSACleanup.restype = wintypes.INT

WSAAddressToStringW = windll.Ws2_32.WSAAddressToStringW
WSAAddressToStringW.argtypes = [
    ctypes.POINTER(SOCKADDR), wintypes.DWORD, wintypes.LPVOID,
    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
WSAAddressToStringW.restype = wintypes.INT

Ws2_32 = windll.Ws2_32
Ws2_32.inet_ntoa.restype = ctypes.c_char_p


def init_wsa(version=VERSION_2_2):
    wsadata = WSADATA()
    WSAStartup(version, ctypes.byref(wsadata))
