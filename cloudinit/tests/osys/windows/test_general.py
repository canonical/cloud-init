# Copyright (C) 2015 Canonical Ltd.
# Copyright 2015 Cloudbase Solutions Srl
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

import importlib
import unittest

try:
    import unittest.mock
except ImportError:
    import mock

from cloudinit import exceptions


class TestsWindowsGeneral(unittest.TestCase):

    def setUp(self):
        self._ctypes_mock = mock.MagicMock()
        self._win32process_mock = mock.Mock()

        self._module_patcher = mock.patch.dict(
            'sys.modules',
            {'win32process': self._win32process_mock,
             'ctypes': self._ctypes_mock})

        self._module_patcher.start()
        self._general_module = importlib.import_module(
            "cloudinit.osys.windows.general")
        self._kernel32 = importlib.import_module(
            "cloudinit.osys.windows.util.kernel32")
        self._windll_mock = self._ctypes_mock.windll
        self._general = self._general_module.General()

    def tearDown(self):
        self._module_patcher.stop()

    def _test_check_os_version(self, ret_value, error_value=None):
        self._windll_mock.kernel32.VerSetConditionMask.return_value = 2
        self._windll_mock.kernel32.VerifyVersionInfoW.return_value = ret_value
        self._windll_mock.kernel32.GetLastError.return_value = error_value

        old_version = self._kernel32.ERROR_OLD_WIN_VERSION

        if error_value and error_value is not old_version:
            self.assertRaises(exceptions.CloudinitError,
                              self._general.check_os_version, 3, 1, 2)
            self._kernel32.GetLastError.assert_called_once_with()

        else:
            response = self._general.check_os_version(3, 1, 2)

            self._ctypes_mock.sizeof.assert_called_once_with(
                self._kernel32.Win32_OSVERSIONINFOEX_W)
            self.assertEqual(
                3, self._windll_mock.kernel32.VerSetConditionMask.call_count)

            self._windll_mock.kernel32.VerifyVersionInfoW.assert_called_with(
                self._ctypes_mock.byref.return_value, 1 | 2 | 3 | 7, 2)

            if error_value is old_version:
                self._windll_mock.kernel32.GetLastError.assert_called_with()
                self.assertFalse(response)
            else:
                self.assertTrue(response)

    def test_check_os_version(self):
        m = mock.MagicMock()
        self._test_check_os_version(ret_value=m)

    def test_check_os_version_expect_false(self):
        self._test_check_os_version(
            ret_value=None, error_value=self._kernel32.ERROR_OLD_WIN_VERSION)

    @mock.patch('os.path.expandvars')
    def test_system32_dir(self, mock_expandvars):
        path = "system32"
        mock_expandvars.return_value = path
        response = self._general.system32_dir()

        mock_expandvars.assert_called_once_with('%windir%\\{}'.format(path))
        self.assertEqual(path, response)

    @mock.patch('os.path.expandvars')
    def test_sysnative_dir(self, mock_expandvars):
        path = "sysnative"
        mock_expandvars.return_value = path
        response = self._general.sysnative_dir()

        mock_expandvars.assert_called_once_with('%windir%\\{}'.format(path))
        self.assertEqual(path, response)

    def test_is_wow64(self):
        result = self._general.is_wow64()

        self._win32process_mock.IsWow64Process.assert_called_once_with()
        self.assertEqual(self._win32process_mock.IsWow64Process.return_value,
                         result)

    @mock.patch('os.path.isdir')
    @mock.patch('cloudinit.osys.windows.general.General.sysnative_dir')
    @mock.patch('cloudinit.osys.windows.general.General._is_64bit_arch')
    @mock.patch('cloudinit.osys.windows.general.General.syswow64_dir')
    @mock.patch('cloudinit.osys.windows.general.General.system32_dir')
    def _test_get_system_dir(self, mock_get_system32_dir,
                             mock_get_syswow64_dir,
                             mock_is_64bit_arch,
                             mock_get_sysnative_dir,
                             mock_isdir, sysnative, arches):
        mock_get_system32_dir.return_value = "system32"
        mock_get_syswow64_dir.return_value = "syswow64"
        mock_get_sysnative_dir.return_value = "sysnative"
        mock_is_64bit_arch.return_value = arches.startswith("64")
        mock_isdir.return_value = (arches == "32on64")

        expect_dict = {
            "32on32": {
                False: (
                    "system32",
                    [mock_is_64bit_arch, mock_get_system32_dir]
                ),
                True: (
                    "system32",
                    [mock_get_system32_dir]
                )
            },
            "32on64": {
                False: (
                    "system32",
                    [mock_is_64bit_arch, mock_get_system32_dir]
                ),
                True: (
                    "sysnative",
                    [(mock_isdir, "sysnative")]
                )
            },
            "64on64": {
                False: (
                    "syswow64",
                    [mock_is_64bit_arch, mock_get_syswow64_dir]
                ),
                True: (
                    "system32",
                    [mock_get_system32_dir]
                )
            }
        }
        response = self._general.system_dir(sysnative=sysnative)
        expect, calls = expect_dict[arches][sysnative]
        self.assertEqual(expect, response)
        for call in calls:
            if isinstance(call, tuple):
                call, arg = call
                call.assert_called_once_with(arg)
            else:
                call.assert_called_once_with()

    def test_system_dir_32on32(self):
        arches = "32on32"
        self._test_get_system_dir(sysnative=False, arches=arches)
        self._test_get_system_dir(sysnative=True, arches=arches)

    def test_system_dir_32on64(self):
        arches = "32on64"
        self._test_get_system_dir(sysnative=False, arches=arches)
        self._test_get_system_dir(sysnative=True, arches=arches)

    def test_ssystem_dir_64on64(self):
        arches = "64on64"
        self._test_get_system_dir(sysnative=False, arches=arches)
        self._test_get_system_dir(sysnative=True, arches=arches)
