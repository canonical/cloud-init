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
   import unittest.mock as mock
except ImportError:
   import mock

from cloudinit import exceptions


class TestNetworkWindows(unittest.TestCase):

    def setUp(self):
        self._ctypes_mock = mock.MagicMock()
        self._moves_mock = mock.MagicMock()
        self._win32com_mock = mock.MagicMock()
        self._wmi_mock = mock.MagicMock()

        self._module_patcher = mock.patch.dict(
            'sys.modules',
            {'ctypes': self._ctypes_mock,
             'win32com': self._win32com_mock,
             'wmi': self._wmi_mock,
             'six.moves': self._moves_mock})

        self._module_patcher.start()

        self.network_module = importlib.import_module(
            'cloudinit.osys.windows.network')
        self.network_module.iphlpapi = mock.MagicMock()
        self.network_module.kernel32 = mock.MagicMock()
        self.network_module.ws2_32 = mock.MagicMock()

        self.network = self.network_module.Network()

    def tearDown(self):
        self._module_patcher.stop()

    def test_format_mac_address(self):
        phys_address = [00, 00, 00, 00]
        response = self.network_module._format_mac_address(
            phys_address=phys_address,
            phys_address_len=4)
        self.assertEqual("00:00:00:00", response)

    def _test_socket_addr_to_str(self, ret_val):
        mock_socket_addr = mock.MagicMock()

        mock_create_unicode_buffer = self._ctypes_mock.create_unicode_buffer
        mock_byref = self._ctypes_mock.byref

        self.network_module.ws2_32.WSAAddressToStringW.return_value = ret_val

        if ret_val:
            self.assertRaises(exceptions.CloudinitError,
                              self.network_module._socket_addr_to_str,
                              mock_socket_addr)
            self.network_module.ws2_32.WSAGetLastError.assert_called_once_with()
        else:
            response = self.network_module._socket_addr_to_str(mock_socket_addr)
            self.assertEqual(mock_create_unicode_buffer.return_value.value,
                             response)

        self._ctypes_mock.wintypes.DWORD.assert_called_once_with(256)
        mock_create_unicode_buffer.assert_called_once_with(256)

        self.network_module.ws2_32.WSAAddressToStringW.assert_called_once_with(
            mock_socket_addr.lpSockaddr, mock_socket_addr.iSockaddrLength,
            None, mock_create_unicode_buffer.return_value,
            mock_byref.return_value)

        mock_byref.assert_called_once_with(
            self._ctypes_mock.wintypes.DWORD.return_value)

    def test_socket_addr_to_str(self):
        self._test_socket_addr_to_str(ret_val=None)

    def test_socket_addr_to_str_fail(self):
        self._test_socket_addr_to_str(ret_val=1)

    def _test_get_registry_dhcp_server(self, dhcp_server, exception=None):
        fake_adapter = mock.sentinel.fake_adapter_name
        self._moves_mock.winreg.QueryValueEx.return_value = [dhcp_server]

        if exception:
            self._moves_mock.winreg.QueryValueEx.side_effect = [exception]

            if exception.errno != 2:
                self.assertRaises(exceptions.CloudinitError,
                                  self.network_module._get_registry_dhcp_server,
                                  fake_adapter)
        else:
            response = self.network_module._get_registry_dhcp_server(fake_adapter)
            if dhcp_server == "255.255.255.255":
                self.assertEqual(None, response)
            else:
                self.assertEqual(dhcp_server, response)

            self._moves_mock.winreg.OpenKey.assert_called_once_with(
                self._moves_mock.winreg.HKEY_LOCAL_MACHINE,
                "SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\"
                "Interfaces\\%s" % fake_adapter, 0,
                self._moves_mock.winreg.KEY_READ)

            self._moves_mock.winreg.QueryValueEx.assert_called_once_with(
                self._moves_mock.winreg.OpenKey.return_value.__enter__(),
                "DhcpServer")

    def test_get_registry_dhcp_server(self):
        self._test_get_registry_dhcp_server(
            dhcp_server=mock.sentinel.dhcp_server)

    def test_get_registry_dhcp_server_expected(self):
        self._test_get_registry_dhcp_server(dhcp_server="255.255.255.255")

    def test_get_registry_dhcp_server_expeption_not_found(self):
        ex = exceptions.CloudinitError()
        ex.errno = 2
        self._test_get_registry_dhcp_server(dhcp_server="", exception=ex)

    def test_get_registry_dhcp_server_expeption_other(self):
        ex = exceptions.CloudinitError()
        ex.errno = 3
        self._test_get_registry_dhcp_server(dhcp_server="", exception=ex)

    @mock.patch('cloudinit.osys.windows.network._format_mac_address')
    @mock.patch('cloudinit.osys.windows.network._socket_addr_to_str')
    @mock.patch('cloudinit.osys.windows.network'
                '._get_registry_dhcp_server')
    def _test_interfaces(self, mock_get_registry_dhcp_server,
                         mock_socket_addr_to_str,
                         mock_format_mac_address,
                         ret_val, p, ret_val2, xp_data_length):
        self.maxDiff = None

        mock_byref = self._ctypes_mock.byref
        mock_cast = self._ctypes_mock.cast
        mock_POINTER = self._ctypes_mock.POINTER

        self.network_module.iphlpapi.GetAdaptersAddresses.side_effect = [ret_val,
                                                                  ret_val2]
        self.network_module.kernel32.HeapAlloc.return_value = p
        self.network_module.iphlpapi.IP_ADAPTER_DHCP_ENABLED = True
        self.network_module.iphlpapi.IP_ADAPTER_IPV4_ENABLED = True
        self.network_module.iphlpapi.IP_ADAPTER_ADDRESSES_SIZE_2003 = xp_data_length

        p_curr_addr = mock.MagicMock()

        compare_cast = []
        net_adapters = []
        compare_socket_addr_to_str = []

        mock_cast.side_effect = [p_curr_addr, None, None]
        curr_addr = p_curr_addr.contents
        curr_addr.Flags = True
        curr_addr.Union1.Struct1.Length = 2
        curr_addr.Dhcpv4Server.iSockaddrLength = True

        p_unicast_addr = curr_addr.FirstUnicastAddress
        unicast_addr = p_unicast_addr.contents
        unicast_addresses = [
            (mock_socket_addr_to_str.return_value,
             unicast_addr.Address.lpSockaddr.contents.sa_family)]

        compare_GetAdaptersAddresses = [mock.call(
            self.network_module.ws2_32.AF_UNSPEC,
            self.network_module.iphlpapi.GAA_FLAG_SKIP_ANYCAST,
            None, None, mock_byref.return_value)]

        if not p:
            self.assertRaises(exceptions.CloudinitError,
                              self.network.interfaces)

        if ret_val2 and ret_val2 != self.network_module.kernel32.ERROR_NO_DATA:
            self.assertRaises(exceptions.CloudinitError,
                              self.network.interfaces)
            compare_cast.append(mock.call(p, mock_POINTER.return_value))

            compare_GetAdaptersAddresses.append(mock.call(
                self.network_module.ws2_32.AF_UNSPEC,
                self.network_module.iphlpapi.GAA_FLAG_SKIP_ANYCAST, None,
                p_curr_addr, mock_byref.return_value))

        else:
            response = self.network.interfaces()

            if ret_val == self.network_module.kernel32.ERROR_NO_DATA:
                self.assertEqual([], response)

            elif ret_val == self.network_module.kernel32.ERROR_BUFFER_OVERFLOW:
                self.network_module.kernel32.GetProcessHeap.assert_called_once_with()

                self.network_module.kernel32.HeapAlloc.assert_called_once_with(
                    self.network_module.kernel32.GetProcessHeap.return_value, 0,
                    self._ctypes_mock.wintypes.ULONG.return_value.value)

                self.network_module.ws2_32.init_wsa.assert_called_once_with()
                compare_cast.append(mock.call(p, mock_POINTER.return_value))

                compare_GetAdaptersAddresses.append(mock.call(
                    self.network_module.ws2_32.AF_UNSPEC,
                    self.network_module.iphlpapi.GAA_FLAG_SKIP_ANYCAST, None,
                    p_curr_addr, mock_byref.return_value))

                if ret_val2 == self.network_module.kernel32.ERROR_NO_DATA:
                    self.assertEqual([], response)

                else:
                    compare_cast.append(mock.call(p_unicast_addr.contents.Next,
                                                  mock_POINTER.return_value))

                    mock_format_mac_address.assert_called_once_with(
                        p_curr_addr.contents.PhysicalAddress,
                        p_curr_addr.contents.PhysicalAddressLength)

                    if not curr_addr.Union1.Struct1.Length <= xp_data_length:
                        dhcp_server = mock_socket_addr_to_str.return_value
                        compare_socket_addr_to_str.append(
                            mock.call(curr_addr.Dhcpv4Server |
                                      curr_addr.Dhcpv6Server))
                    else:
                        dhcp_server = \
                            mock_get_registry_dhcp_server.return_value

                        mock_get_registry_dhcp_server.assert_called_once_with(
                            curr_addr.AdapterName)

                    compare_cast.append(mock.call(curr_addr.Next,
                                                  mock_POINTER.return_value))
                    self.network_module.kernel32.HeapFree.assert_called_once_with(
                        self.network_module.kernel32.GetProcessHeap.return_value, 0,
                        p)

                    self.network_module.ws2_32.WSACleanup.assert_called_once_with()

                    compare_socket_addr_to_str.append(mock.call(
                        unicast_addr.Address))

                    net_adapters.append(
                        self.network_module.Interface(
                            mac=mock_format_mac_address.return_value,
                            name=curr_addr.AdapterName,
                            index=curr_addr.Union1.Struct1.IfIndex,
                            mtu=curr_addr.Mtu,
                            dhcp_server=dhcp_server,
                            dhcp_enabled=True))

                    self.assertEqual(net_adapters, response)

        self.assertEqual(compare_cast, mock_cast.call_args_list)

        self.assertEqual(
            compare_GetAdaptersAddresses,
            self.network_module.iphlpapi.GetAdaptersAddresses.call_args_list)

    def test_interfaces_no_data(self):
        self._test_interfaces(
            ret_val=self.network_module.kernel32.ERROR_NO_DATA,
            p=True, ret_val2=self.network_module.kernel32.ERROR_NO_DATA,
            xp_data_length=3)

    def test_interfaces_overflow_and_no_data(self):
        self._test_interfaces(
            ret_val=self.network_module.kernel32.ERROR_BUFFER_OVERFLOW,
            p=True, ret_val2=self.network_module.kernel32.ERROR_NO_DATA,
            xp_data_length=3)

    def test_interfaces_other_ret_val(self):
        self._test_interfaces(
            ret_val=self.network_module.kernel32.ERROR_BUFFER_OVERFLOW,
            p=True, ret_val2=mock.sentinel.other_return_value,
            xp_data_length=3)

    def test_interfaces_overflow(self):
        self._test_interfaces(
            ret_val=self.network_module.kernel32.ERROR_BUFFER_OVERFLOW,
            p=True, ret_val2=None,
            xp_data_length=3)

    def test_interfaces_overflow_xp_data(self):
        self._test_interfaces(
            ret_val=self.network_module.kernel32.ERROR_BUFFER_OVERFLOW,
            p=True, ret_val2=None,
            xp_data_length=0)
