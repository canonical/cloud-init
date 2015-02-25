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
import logging
import os
import struct

import win32process

from cloudinit import exceptions
from cloudinit.osys import general
from cloudinit.osys.windows.util import kernel32


LOG = logging.getLogger(__name__)


class General(general.General):
    """General utilities namespace for Windows."""

    @staticmethod
    def check_os_version(major, minor, build=0):
        vi = kernel32.Win32_OSVERSIONINFOEX_W()
        vi.dwOSVersionInfoSize = ctypes.sizeof(
            kernel32.Win32_OSVERSIONINFOEX_W)

        vi.dwMajorVersion = major
        vi.dwMinorVersion = minor
        vi.dwBuildNumber = build

        mask = 0
        for type_mask in [kernel32.VER_MAJORVERSION,
                          kernel32.VER_MINORVERSION,
                          kernel32.VER_BUILDNUMBER]:
            mask = kernel32.VerSetConditionMask(mask, type_mask,
                                                kernel32.VER_GREATER_EQUAL)

        type_mask = (kernel32.VER_MAJORVERSION |
                     kernel32.VER_MINORVERSION |
                     kernel32.VER_BUILDNUMBER)
        ret_val = kernel32.VerifyVersionInfoW(ctypes.byref(vi), type_mask,
                                              mask)
        if ret_val:
            return True
        else:
            err = kernel32.GetLastError()
            if err == kernel32.ERROR_OLD_WIN_VERSION:
                return False
            else:
                raise exceptions.CloudinitError(
                    "VerifyVersionInfo failed with error: %s" % err)

    @staticmethod
    def _is_64bit_arch():
        # interpreter's bits
        return struct.calcsize("P") == 8

    @staticmethod
    def system32_dir():
        return os.path.expandvars('%windir%\\system32')

    @staticmethod
    def sysnative_dir():
        return os.path.expandvars('%windir%\\sysnative')

    @staticmethod
    def syswow64_dir():
        return os.path.expandvars('%windir%\\syswow64')

    @staticmethod
    def is_wow64():
        return win32process.IsWow64Process()

    def system_dir(self, sysnative=True):
        if sysnative and os.path.isdir(self.sysnative_dir()):
            return self.sysnative_dir()
        if not sysnative and self._is_64bit_arch():
            return self.syswow64_dir()
        return self.system32_dir()
