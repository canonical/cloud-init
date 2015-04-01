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

ERROR_BUFFER_OVERFLOW = 111
ERROR_NO_DATA = 232


class GUID(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", wintypes.BYTE * 8)]

    def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
        self.data1 = l
        self.data2 = w1
        self.data3 = w2
        self.data4[0] = b1
        self.data4[1] = b2
        self.data4[2] = b3
        self.data4[3] = b4
        self.data4[4] = b5
        self.data4[5] = b6
        self.data4[6] = b7
        self.data4[7] = b8


class Win32_OSVERSIONINFOEX_W(ctypes.Structure):
    _fields_ = [
        ('dwOSVersionInfoSize', wintypes.DWORD),
        ('dwMajorVersion', wintypes.DWORD),
        ('dwMinorVersion', wintypes.DWORD),
        ('dwBuildNumber', wintypes.DWORD),
        ('dwPlatformId', wintypes.DWORD),
        ('szCSDVersion', wintypes.WCHAR * 128),
        ('wServicePackMajor', wintypes.DWORD),
        ('wServicePackMinor', wintypes.DWORD),
        ('wSuiteMask', wintypes.DWORD),
        ('wProductType', wintypes.BYTE),
        ('wReserved', wintypes.BYTE)
    ]


GetLastError = windll.kernel32.GetLastError

GetProcessHeap = windll.kernel32.GetProcessHeap
GetProcessHeap.argtypes = []
GetProcessHeap.restype = wintypes.HANDLE

HeapAlloc = windll.kernel32.HeapAlloc
# Note: wintypes.ULONG must be replaced with a 64 bit variable on x64
HeapAlloc.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.ULONG]
HeapAlloc.restype = wintypes.LPVOID

HeapFree = windll.kernel32.HeapFree
HeapFree.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID]
HeapFree.restype = wintypes.BOOL

SetComputerNameExW = windll.kernel32.SetComputerNameExW

VerifyVersionInfoW = windll.kernel32.VerifyVersionInfoW
VerSetConditionMask = windll.kernel32.VerSetConditionMask

VerifyVersionInfoW.argtypes = [
    ctypes.POINTER(Win32_OSVERSIONINFOEX_W),
    wintypes.DWORD, wintypes.ULARGE_INTEGER]
VerifyVersionInfoW.restype = wintypes.BOOL

VerSetConditionMask.argtypes = [wintypes.ULARGE_INTEGER,
                                wintypes.DWORD,
                                wintypes.BYTE]
VerSetConditionMask.restype = wintypes.ULARGE_INTEGER

ERROR_OLD_WIN_VERSION = 1150
VER_MAJORVERSION = 1
VER_MINORVERSION = 2
VER_BUILDNUMBER = 4
VER_GREATER_EQUAL = 3
