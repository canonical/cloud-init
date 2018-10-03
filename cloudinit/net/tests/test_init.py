# This file is part of cloud-init. See LICENSE file for license information.

import copy
import errno
import mock
import os
import textwrap
import yaml

import cloudinit.net as net
from cloudinit.util import ensure_file, write_file, ProcessExecutionError
from cloudinit.tests.helpers import CiTestCase


class TestSysDevPath(CiTestCase):

    def test_sys_dev_path(self):
        """sys_dev_path returns a path under SYS_CLASS_NET for a device."""
        dev = 'something'
        path = 'attribute'
        expected = net.SYS_CLASS_NET + dev + '/' + path
        self.assertEqual(expected, net.sys_dev_path(dev, path))

    def test_sys_dev_path_without_path(self):
        """When path param isn't provided it defaults to empty string."""
        dev = 'something'
        expected = net.SYS_CLASS_NET + dev + '/'
        self.assertEqual(expected, net.sys_dev_path(dev))


class TestReadSysNet(CiTestCase):
    with_logs = True

    def setUp(self):
        super(TestReadSysNet, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_read_sys_net_strips_contents_of_sys_path(self):
        """read_sys_net strips whitespace from the contents of a sys file."""
        content = 'some stuff with trailing whitespace\t\r\n'
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), content)
        self.assertEqual(content.strip(), net.read_sys_net('dev', 'attr'))

    def test_read_sys_net_reraises_oserror(self):
        """read_sys_net raises OSError/IOError when file doesn't exist."""
        # Non-specific Exception because versions of python OSError vs IOError.
        with self.assertRaises(Exception) as context_manager:  # noqa: H202
            net.read_sys_net('dev', 'attr')
        error = context_manager.exception
        self.assertIn('No such file or directory', str(error))

    def test_read_sys_net_handles_error_with_on_enoent(self):
        """read_sys_net handles OSError/IOError with on_enoent if provided."""
        handled_errors = []

        def on_enoent(e):
            handled_errors.append(e)

        net.read_sys_net('dev', 'attr', on_enoent=on_enoent)
        error = handled_errors[0]
        self.assertIsInstance(error, Exception)
        self.assertIn('No such file or directory', str(error))

    def test_read_sys_net_translates_content(self):
        """read_sys_net translates content when translate dict is provided."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), content)
        translate = {"you're welcome": 'de nada'}
        self.assertEqual(
            'de nada',
            net.read_sys_net('dev', 'attr', translate=translate))

    def test_read_sys_net_errors_on_translation_failures(self):
        """read_sys_net raises a KeyError and logs details on failure."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), content)
        with self.assertRaises(KeyError) as context_manager:
            net.read_sys_net('dev', 'attr', translate={})
        error = context_manager.exception
        self.assertEqual('"you\'re welcome"', str(error))
        self.assertIn(
            "Found unexpected (not translatable) value 'you're welcome' in "
            "'{0}dev/attr".format(self.sysdir),
            self.logs.getvalue())

    def test_read_sys_net_handles_handles_with_onkeyerror(self):
        """read_sys_net handles translation errors calling on_keyerror."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), content)
        handled_errors = []

        def on_keyerror(e):
            handled_errors.append(e)

        net.read_sys_net('dev', 'attr', translate={}, on_keyerror=on_keyerror)
        error = handled_errors[0]
        self.assertIsInstance(error, KeyError)
        self.assertEqual('"you\'re welcome"', str(error))

    def test_read_sys_net_safe_false_on_translate_failure(self):
        """read_sys_net_safe returns False on translation failures."""
        content = "you're welcome\n"
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), content)
        self.assertFalse(net.read_sys_net_safe('dev', 'attr', translate={}))

    def test_read_sys_net_safe_returns_false_on_noent_failure(self):
        """read_sys_net_safe returns False on file not found failures."""
        self.assertFalse(net.read_sys_net_safe('dev', 'attr'))

    def test_read_sys_net_int_returns_none_on_error(self):
        """read_sys_net_safe returns None on failures."""
        self.assertFalse(net.read_sys_net_int('dev', 'attr'))

    def test_read_sys_net_int_returns_none_on_valueerror(self):
        """read_sys_net_safe returns None when content is not an int."""
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), 'NOTINT\n')
        self.assertFalse(net.read_sys_net_int('dev', 'attr'))

    def test_read_sys_net_int_returns_integer_from_content(self):
        """read_sys_net_safe returns None on failures."""
        write_file(os.path.join(self.sysdir, 'dev', 'attr'), '1\n')
        self.assertEqual(1, net.read_sys_net_int('dev', 'attr'))

    def test_is_up_true(self):
        """is_up is True if sys/net/devname/operstate is 'up' or 'unknown'."""
        for state in ['up', 'unknown']:
            write_file(os.path.join(self.sysdir, 'eth0', 'operstate'), state)
            self.assertTrue(net.is_up('eth0'))

    def test_is_up_false(self):
        """is_up is False if sys/net/devname/operstate is 'down' or invalid."""
        for state in ['down', 'incomprehensible']:
            write_file(os.path.join(self.sysdir, 'eth0', 'operstate'), state)
            self.assertFalse(net.is_up('eth0'))

    def test_is_wireless(self):
        """is_wireless is True when /sys/net/devname/wireless exists."""
        self.assertFalse(net.is_wireless('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'wireless'))
        self.assertTrue(net.is_wireless('eth0'))

    def test_is_bridge(self):
        """is_bridge is True when /sys/net/devname/bridge exists."""
        self.assertFalse(net.is_bridge('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'bridge'))
        self.assertTrue(net.is_bridge('eth0'))

    def test_is_bond(self):
        """is_bond is True when /sys/net/devname/bonding exists."""
        self.assertFalse(net.is_bond('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'bonding'))
        self.assertTrue(net.is_bond('eth0'))

    def test_is_vlan(self):
        """is_vlan is True when /sys/net/devname/uevent has DEVTYPE=vlan."""
        ensure_file(os.path.join(self.sysdir, 'eth0', 'uevent'))
        self.assertFalse(net.is_vlan('eth0'))
        content = 'junk\nDEVTYPE=vlan\njunk\n'
        write_file(os.path.join(self.sysdir, 'eth0', 'uevent'), content)
        self.assertTrue(net.is_vlan('eth0'))

    def test_is_connected_when_physically_connected(self):
        """is_connected is True when /sys/net/devname/iflink reports 2."""
        self.assertFalse(net.is_connected('eth0'))
        write_file(os.path.join(self.sysdir, 'eth0', 'iflink'), "2")
        self.assertTrue(net.is_connected('eth0'))

    def test_is_connected_when_wireless_and_carrier_active(self):
        """is_connected is True if wireless /sys/net/devname/carrier is 1."""
        self.assertFalse(net.is_connected('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'wireless'))
        self.assertFalse(net.is_connected('eth0'))
        write_file(os.path.join(self.sysdir, 'eth0', 'carrier'), "1")
        self.assertTrue(net.is_connected('eth0'))

    def test_is_physical(self):
        """is_physical is True when /sys/net/devname/device exists."""
        self.assertFalse(net.is_physical('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'device'))
        self.assertTrue(net.is_physical('eth0'))

    def test_is_present(self):
        """is_present is True when /sys/net/devname exists."""
        self.assertFalse(net.is_present('eth0'))
        ensure_file(os.path.join(self.sysdir, 'eth0', 'device'))
        self.assertTrue(net.is_present('eth0'))


class TestGenerateFallbackConfig(CiTestCase):

    def setUp(self):
        super(TestGenerateFallbackConfig, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)
        self.add_patch('cloudinit.net.util.is_container', 'm_is_container',
                       return_value=False)
        self.add_patch('cloudinit.net.util.udevadm_settle', 'm_settle')

    def test_generate_fallback_finds_connected_eth_with_mac(self):
        """generate_fallback_config finds any connected device with a mac."""
        write_file(os.path.join(self.sysdir, 'eth0', 'carrier'), '1')
        write_file(os.path.join(self.sysdir, 'eth1', 'carrier'), '1')
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth1', 'address'), mac)
        expected = {
            'config': [{'type': 'physical', 'mac_address': mac,
                        'name': 'eth1', 'subnets': [{'type': 'dhcp'}]}],
            'version': 1}
        self.assertEqual(expected, net.generate_fallback_config())

    def test_generate_fallback_finds_dormant_eth_with_mac(self):
        """generate_fallback_config finds any dormant device with a mac."""
        write_file(os.path.join(self.sysdir, 'eth0', 'dormant'), '1')
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth0', 'address'), mac)
        expected = {
            'config': [{'type': 'physical', 'mac_address': mac,
                        'name': 'eth0', 'subnets': [{'type': 'dhcp'}]}],
            'version': 1}
        self.assertEqual(expected, net.generate_fallback_config())

    def test_generate_fallback_finds_eth_by_operstate(self):
        """generate_fallback_config finds any dormant device with a mac."""
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth0', 'address'), mac)
        expected = {
            'config': [{'type': 'physical', 'mac_address': mac,
                        'name': 'eth0', 'subnets': [{'type': 'dhcp'}]}],
            'version': 1}
        valid_operstates = ['dormant', 'down', 'lowerlayerdown', 'unknown']
        for state in valid_operstates:
            write_file(os.path.join(self.sysdir, 'eth0', 'operstate'), state)
            self.assertEqual(expected, net.generate_fallback_config())
        write_file(os.path.join(self.sysdir, 'eth0', 'operstate'), 'noworky')
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_veth(self):
        """generate_fallback_config will skip any veth interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, 'veth0', 'carrier'), '1')
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_bridges(self):
        """generate_fallback_config will skip any bridges interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, 'eth0', 'carrier'), '1')
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth0', 'address'), mac)
        ensure_file(os.path.join(self.sysdir, 'eth0', 'bridge'))
        self.assertIsNone(net.generate_fallback_config())

    def test_generate_fallback_config_skips_bonds(self):
        """generate_fallback_config will skip any bonded interfaces."""
        # A connected veth which gets ignored
        write_file(os.path.join(self.sysdir, 'eth0', 'carrier'), '1')
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth0', 'address'), mac)
        ensure_file(os.path.join(self.sysdir, 'eth0', 'bonding'))
        self.assertIsNone(net.generate_fallback_config())


class TestGetDeviceList(CiTestCase):

    def setUp(self):
        super(TestGetDeviceList, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_get_devicelist_raise_oserror(self):
        """get_devicelist raise any non-ENOENT OSerror."""
        error = OSError('Can not do it')
        error.errno = errno.EPERM  # Set non-ENOENT
        self.m_sys_path.side_effect = error
        with self.assertRaises(OSError) as context_manager:
            net.get_devicelist()
        exception = context_manager.exception
        self.assertEqual('Can not do it', str(exception))

    def test_get_devicelist_empty_without_sys_net(self):
        """get_devicelist returns empty list when missing SYS_CLASS_NET."""
        self.m_sys_path.return_value = 'idontexist'
        self.assertEqual([], net.get_devicelist())

    def test_get_devicelist_empty_with_no_devices_in_sys_net(self):
        """get_devicelist returns empty directoty listing for SYS_CLASS_NET."""
        self.assertEqual([], net.get_devicelist())

    def test_get_devicelist_lists_any_subdirectories_in_sys_net(self):
        """get_devicelist returns a directory listing for SYS_CLASS_NET."""
        write_file(os.path.join(self.sysdir, 'eth0', 'operstate'), 'up')
        write_file(os.path.join(self.sysdir, 'eth1', 'operstate'), 'up')
        self.assertItemsEqual(['eth0', 'eth1'], net.get_devicelist())


class TestGetInterfaceMAC(CiTestCase):

    def setUp(self):
        super(TestGetInterfaceMAC, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_get_interface_mac_false_with_no_mac(self):
        """get_device_list returns False when no mac is reported."""
        ensure_file(os.path.join(self.sysdir, 'eth0', 'bonding'))
        mac_path = os.path.join(self.sysdir, 'eth0', 'address')
        self.assertFalse(os.path.exists(mac_path))
        self.assertFalse(net.get_interface_mac('eth0'))

    def test_get_interface_mac(self):
        """get_interfaces returns the mac from SYS_CLASS_NET/dev/address."""
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth1', 'address'), mac)
        self.assertEqual(mac, net.get_interface_mac('eth1'))

    def test_get_interface_mac_grabs_bonding_address(self):
        """get_interfaces returns the source device mac for bonded devices."""
        source_dev_mac = 'aa:bb:cc:aa:bb:cc'
        bonded_mac = 'dd:ee:ff:dd:ee:ff'
        write_file(os.path.join(self.sysdir, 'eth1', 'address'), bonded_mac)
        write_file(
            os.path.join(self.sysdir, 'eth1', 'bonding_slave', 'perm_hwaddr'),
            source_dev_mac)
        self.assertEqual(source_dev_mac, net.get_interface_mac('eth1'))

    def test_get_interfaces_empty_list_without_sys_net(self):
        """get_interfaces returns an empty list when missing SYS_CLASS_NET."""
        self.m_sys_path.return_value = 'idontexist'
        self.assertEqual([], net.get_interfaces())

    def test_get_interfaces_by_mac_skips_empty_mac(self):
        """Ignore 00:00:00:00:00:00 addresses from get_interfaces_by_mac."""
        empty_mac = '00:00:00:00:00:00'
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth1', 'address'), empty_mac)
        write_file(os.path.join(self.sysdir, 'eth1', 'addr_assign_type'), '0')
        write_file(os.path.join(self.sysdir, 'eth2', 'addr_assign_type'), '0')
        write_file(os.path.join(self.sysdir, 'eth2', 'address'), mac)
        expected = [('eth2', 'aa:bb:cc:aa:bb:cc', None, None)]
        self.assertEqual(expected, net.get_interfaces())

    def test_get_interfaces_by_mac_skips_missing_mac(self):
        """Ignore interfaces without an address from get_interfaces_by_mac."""
        write_file(os.path.join(self.sysdir, 'eth1', 'addr_assign_type'), '0')
        address_path = os.path.join(self.sysdir, 'eth1', 'address')
        self.assertFalse(os.path.exists(address_path))
        mac = 'aa:bb:cc:aa:bb:cc'
        write_file(os.path.join(self.sysdir, 'eth2', 'addr_assign_type'), '0')
        write_file(os.path.join(self.sysdir, 'eth2', 'address'), mac)
        expected = [('eth2', 'aa:bb:cc:aa:bb:cc', None, None)]
        self.assertEqual(expected, net.get_interfaces())


class TestInterfaceHasOwnMAC(CiTestCase):

    def setUp(self):
        super(TestInterfaceHasOwnMAC, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_interface_has_own_mac_false_when_stolen(self):
        """Return False from interface_has_own_mac when address is stolen."""
        write_file(os.path.join(self.sysdir, 'eth1', 'addr_assign_type'), '2')
        self.assertFalse(net.interface_has_own_mac('eth1'))

    def test_interface_has_own_mac_true_when_not_stolen(self):
        """Return False from interface_has_own_mac when mac isn't stolen."""
        valid_assign_types = ['0', '1', '3']
        assign_path = os.path.join(self.sysdir, 'eth1', 'addr_assign_type')
        for _type in valid_assign_types:
            write_file(assign_path, _type)
            self.assertTrue(net.interface_has_own_mac('eth1'))

    def test_interface_has_own_mac_strict_errors_on_absent_assign_type(self):
        """When addr_assign_type is absent, interface_has_own_mac errors."""
        with self.assertRaises(ValueError):
            net.interface_has_own_mac('eth1', strict=True)


@mock.patch('cloudinit.net.util.subp')
class TestEphemeralIPV4Network(CiTestCase):

    with_logs = True

    def setUp(self):
        super(TestEphemeralIPV4Network, self).setUp()
        sys_mock = mock.patch('cloudinit.net.get_sys_class_path')
        self.m_sys_path = sys_mock.start()
        self.sysdir = self.tmp_dir() + '/'
        self.m_sys_path.return_value = self.sysdir
        self.addCleanup(sys_mock.stop)

    def test_ephemeral_ipv4_network_errors_on_missing_params(self, m_subp):
        """No required params for EphemeralIPv4Network can be None."""
        required_params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'prefix_or_mask': '255.255.255.0', 'broadcast': '192.168.2.255'}
        for key in required_params.keys():
            params = copy.deepcopy(required_params)
            params[key] = None
            with self.assertRaises(ValueError) as context_manager:
                net.EphemeralIPv4Network(**params)
            error = context_manager.exception
            self.assertIn('Cannot init network on', str(error))
            self.assertEqual(0, m_subp.call_count)

    def test_ephemeral_ipv4_network_errors_invalid_mask_prefix(self, m_subp):
        """Raise an error when prefix_or_mask is not a netmask or prefix."""
        params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'broadcast': '192.168.2.255'}
        invalid_masks = ('invalid', 'invalid.', '123.123.123')
        for error_val in invalid_masks:
            params['prefix_or_mask'] = error_val
            with self.assertRaises(ValueError) as context_manager:
                with net.EphemeralIPv4Network(**params):
                    pass
            error = context_manager.exception
            self.assertIn('Cannot setup network: netmask', str(error))
            self.assertEqual(0, m_subp.call_count)

    def test_ephemeral_ipv4_network_performs_teardown(self, m_subp):
        """EphemeralIPv4Network performs teardown on the device if setup."""
        expected_setup_calls = [
            mock.call(
                ['ip', '-family', 'inet', 'addr', 'add', '192.168.2.2/24',
                 'broadcast', '192.168.2.255', 'dev', 'eth0'],
                capture=True, update_env={'LANG': 'C'}),
            mock.call(
                ['ip', '-family', 'inet', 'link', 'set', 'dev', 'eth0', 'up'],
                capture=True)]
        expected_teardown_calls = [
            mock.call(
                ['ip', '-family', 'inet', 'link', 'set', 'dev', 'eth0',
                 'down'], capture=True),
            mock.call(
                ['ip', '-family', 'inet', 'addr', 'del', '192.168.2.2/24',
                 'dev', 'eth0'], capture=True)]
        params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'prefix_or_mask': '255.255.255.0', 'broadcast': '192.168.2.255'}
        with net.EphemeralIPv4Network(**params):
            self.assertEqual(expected_setup_calls, m_subp.call_args_list)
        m_subp.assert_has_calls(expected_teardown_calls)

    def test_ephemeral_ipv4_network_noop_when_configured(self, m_subp):
        """EphemeralIPv4Network handles exception when address is setup.

        It performs no cleanup as the interface was already setup.
        """
        params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'prefix_or_mask': '255.255.255.0', 'broadcast': '192.168.2.255'}
        m_subp.side_effect = ProcessExecutionError(
            '', 'RTNETLINK answers: File exists', 2)
        expected_calls = [
            mock.call(
                ['ip', '-family', 'inet', 'addr', 'add', '192.168.2.2/24',
                 'broadcast', '192.168.2.255', 'dev', 'eth0'],
                capture=True, update_env={'LANG': 'C'})]
        with net.EphemeralIPv4Network(**params):
            pass
        self.assertEqual(expected_calls, m_subp.call_args_list)
        self.assertIn(
            'Skip ephemeral network setup, eth0 already has address',
            self.logs.getvalue())

    def test_ephemeral_ipv4_network_with_prefix(self, m_subp):
        """EphemeralIPv4Network takes a valid prefix to setup the network."""
        params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'prefix_or_mask': '24', 'broadcast': '192.168.2.255'}
        for prefix_val in ['24', 16]:  # prefix can be int or string
            params['prefix_or_mask'] = prefix_val
            with net.EphemeralIPv4Network(**params):
                pass
        m_subp.assert_has_calls([mock.call(
            ['ip', '-family', 'inet', 'addr', 'add', '192.168.2.2/24',
             'broadcast', '192.168.2.255', 'dev', 'eth0'],
            capture=True, update_env={'LANG': 'C'})])
        m_subp.assert_has_calls([mock.call(
            ['ip', '-family', 'inet', 'addr', 'add', '192.168.2.2/16',
             'broadcast', '192.168.2.255', 'dev', 'eth0'],
            capture=True, update_env={'LANG': 'C'})])

    def test_ephemeral_ipv4_network_with_new_default_route(self, m_subp):
        """Add the route when router is set and no default route exists."""
        params = {
            'interface': 'eth0', 'ip': '192.168.2.2',
            'prefix_or_mask': '255.255.255.0', 'broadcast': '192.168.2.255',
            'router': '192.168.2.1'}
        m_subp.return_value = '', ''  # Empty response from ip route gw check
        expected_setup_calls = [
            mock.call(
                ['ip', '-family', 'inet', 'addr', 'add', '192.168.2.2/24',
                 'broadcast', '192.168.2.255', 'dev', 'eth0'],
                capture=True, update_env={'LANG': 'C'}),
            mock.call(
                ['ip', '-family', 'inet', 'link', 'set', 'dev', 'eth0', 'up'],
                capture=True),
            mock.call(
                ['ip', 'route', 'show', '0.0.0.0/0'], capture=True),
            mock.call(['ip', '-4', 'route', 'add', '192.168.2.1',
                       'dev', 'eth0', 'src', '192.168.2.2'], capture=True),
            mock.call(
                ['ip', '-4', 'route', 'add', 'default', 'via',
                 '192.168.2.1', 'dev', 'eth0'], capture=True)]
        expected_teardown_calls = [
            mock.call(['ip', '-4', 'route', 'del', 'default', 'dev', 'eth0'],
                      capture=True),
            mock.call(['ip', '-4', 'route', 'del', '192.168.2.1',
                       'dev', 'eth0', 'src', '192.168.2.2'], capture=True),
        ]

        with net.EphemeralIPv4Network(**params):
            self.assertEqual(expected_setup_calls, m_subp.call_args_list)
        m_subp.assert_has_calls(expected_teardown_calls)


class TestApplyNetworkCfgNames(CiTestCase):
    V1_CONFIG = textwrap.dedent("""\
        version: 1
        config:
            - type: physical
              name: interface0
              mac_address: "52:54:00:12:34:00"
              subnets:
                  - type: static
                    address: 10.0.2.15
                    netmask: 255.255.255.0
                    gateway: 10.0.2.2
    """)
    V2_CONFIG = textwrap.dedent("""\
      version: 2
      ethernets:
          interface0:
            match:
              macaddress: "52:54:00:12:34:00"
            addresses:
              - 10.0.2.15/24
            gateway4: 10.0.2.2
            set-name: interface0
    """)

    V2_CONFIG_NO_SETNAME = textwrap.dedent("""\
      version: 2
      ethernets:
          interface0:
            match:
              macaddress: "52:54:00:12:34:00"
            addresses:
              - 10.0.2.15/24
            gateway4: 10.0.2.2
    """)

    V2_CONFIG_NO_MAC = textwrap.dedent("""\
      version: 2
      ethernets:
          interface0:
            match:
              driver: virtio-net
            addresses:
              - 10.0.2.15/24
            gateway4: 10.0.2.2
            set-name: interface0
    """)

    @mock.patch('cloudinit.net.device_devid')
    @mock.patch('cloudinit.net.device_driver')
    @mock.patch('cloudinit.net._rename_interfaces')
    def test_apply_v1_renames(self, m_rename_interfaces, m_device_driver,
                              m_device_devid):
        m_device_driver.return_value = 'virtio_net'
        m_device_devid.return_value = '0x15d8'

        net.apply_network_config_names(yaml.load(self.V1_CONFIG))

        call = ['52:54:00:12:34:00', 'interface0', 'virtio_net', '0x15d8']
        m_rename_interfaces.assert_called_with([call])

    @mock.patch('cloudinit.net.device_devid')
    @mock.patch('cloudinit.net.device_driver')
    @mock.patch('cloudinit.net._rename_interfaces')
    def test_apply_v2_renames(self, m_rename_interfaces, m_device_driver,
                              m_device_devid):
        m_device_driver.return_value = 'virtio_net'
        m_device_devid.return_value = '0x15d8'

        net.apply_network_config_names(yaml.load(self.V2_CONFIG))

        call = ['52:54:00:12:34:00', 'interface0', 'virtio_net', '0x15d8']
        m_rename_interfaces.assert_called_with([call])

    @mock.patch('cloudinit.net._rename_interfaces')
    def test_apply_v2_renames_skips_without_setname(self, m_rename_interfaces):
        net.apply_network_config_names(yaml.load(self.V2_CONFIG_NO_SETNAME))
        m_rename_interfaces.assert_called_with([])

    @mock.patch('cloudinit.net._rename_interfaces')
    def test_apply_v2_renames_skips_without_mac(self, m_rename_interfaces):
        net.apply_network_config_names(yaml.load(self.V2_CONFIG_NO_MAC))
        m_rename_interfaces.assert_called_with([])

    def test_apply_v2_renames_raises_runtime_error_on_unknown_version(self):
        with self.assertRaises(RuntimeError):
            net.apply_network_config_names(yaml.load("version: 3"))
