# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit.sources import DataSourceOpenNebula as ds
from cloudinit import util
from cloudinit.tests.helpers import mock, populate_dir, CiTestCase

import os
import pwd
import unittest


TEST_VARS = {
    'VAR1': 'single',
    'VAR2': 'double word',
    'VAR3': 'multi\nline\n',
    'VAR4': "'single'",
    'VAR5': "'double word'",
    'VAR6': "'multi\nline\n'",
    'VAR7': 'single\\t',
    'VAR8': 'double\\tword',
    'VAR9': 'multi\\t\nline\n',
    'VAR10': '\\',  # expect '\'
    'VAR11': '\'',  # expect '
    'VAR12': '$',   # expect $
}

INVALID_CONTEXT = ';'
USER_DATA = '#cloud-config\napt_upgrade: true'
SSH_KEY = 'ssh-rsa AAAAB3NzaC1....sIkJhq8wdX+4I3A4cYbYP ubuntu@server-460-%i'
HOSTNAME = 'foo.example.com'
PUBLIC_IP = '10.0.0.3'
MACADDR = '02:00:0a:12:01:01'
IP_BY_MACADDR = '10.18.1.1'
IP4_PREFIX = '24'
IP6_GLOBAL = '2001:db8:1:0:400:c0ff:fea8:1ba'
IP6_ULA = 'fd01:dead:beaf:0:400:c0ff:fea8:1ba'
IP6_GW = '2001:db8:1::ffff'
IP6_PREFIX = '48'

DS_PATH = "cloudinit.sources.DataSourceOpenNebula"


class TestOpenNebulaDataSource(CiTestCase):
    parsed_user = None
    allowed_subp = ['bash']

    def setUp(self):
        super(TestOpenNebulaDataSource, self).setUp()
        self.tmp = self.tmp_dir()
        self.paths = helpers.Paths(
            {'cloud_dir': self.tmp, 'run_dir': self.tmp})

        # defaults for few tests
        self.ds = ds.DataSourceOpenNebula
        self.seed_dir = os.path.join(self.paths.seed_dir, "opennebula")
        self.sys_cfg = {'datasource': {'OpenNebula': {'dsmode': 'local'}}}

        # we don't want 'sudo' called in tests. so we patch switch_user_cmd
        def my_switch_user_cmd(user):
            self.parsed_user = user
            return []

        self.switch_user_cmd_real = ds.switch_user_cmd
        ds.switch_user_cmd = my_switch_user_cmd

    def tearDown(self):
        ds.switch_user_cmd = self.switch_user_cmd_real
        super(TestOpenNebulaDataSource, self).tearDown()

    def test_get_data_non_contextdisk(self):
        orig_find_devs_with = util.find_devs_with
        try:
            # dont' try to lookup for CDs
            util.find_devs_with = lambda n: []
            dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
            ret = dsrc.get_data()
            self.assertFalse(ret)
        finally:
            util.find_devs_with = orig_find_devs_with

    def test_get_data_broken_contextdisk(self):
        orig_find_devs_with = util.find_devs_with
        try:
            # dont' try to lookup for CDs
            util.find_devs_with = lambda n: []
            populate_dir(self.seed_dir, {'context.sh': INVALID_CONTEXT})
            dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
            self.assertRaises(ds.BrokenContextDiskDir, dsrc.get_data)
        finally:
            util.find_devs_with = orig_find_devs_with

    def test_get_data_invalid_identity(self):
        orig_find_devs_with = util.find_devs_with
        try:
            # generate non-existing system user name
            sys_cfg = self.sys_cfg
            invalid_user = 'invalid'
            while not sys_cfg['datasource']['OpenNebula'].get('parseuser'):
                try:
                    pwd.getpwnam(invalid_user)
                    invalid_user += 'X'
                except KeyError:
                    sys_cfg['datasource']['OpenNebula']['parseuser'] = \
                        invalid_user

            # dont' try to lookup for CDs
            util.find_devs_with = lambda n: []
            populate_context_dir(self.seed_dir, {'KEY1': 'val1'})
            dsrc = self.ds(sys_cfg=sys_cfg, distro=None, paths=self.paths)
            self.assertRaises(ds.BrokenContextDiskDir, dsrc.get_data)
        finally:
            util.find_devs_with = orig_find_devs_with

    def test_get_data(self):
        orig_find_devs_with = util.find_devs_with
        try:
            # dont' try to lookup for CDs
            util.find_devs_with = lambda n: []
            populate_context_dir(self.seed_dir, {'KEY1': 'val1'})
            dsrc = self.ds(sys_cfg=self.sys_cfg, distro=None, paths=self.paths)
            ret = dsrc.get_data()
            self.assertTrue(ret)
        finally:
            util.find_devs_with = orig_find_devs_with
        self.assertEqual('opennebula', dsrc.cloud_name)
        self.assertEqual('opennebula', dsrc.platform_type)
        self.assertEqual(
            'seed-dir (%s/seed/opennebula)' % self.tmp, dsrc.subplatform)

    def test_seed_dir_non_contextdisk(self):
        self.assertRaises(ds.NonContextDiskDir, ds.read_context_disk_dir,
                          self.seed_dir)

    def test_seed_dir_empty1_context(self):
        populate_dir(self.seed_dir, {'context.sh': ''})
        results = ds.read_context_disk_dir(self.seed_dir)

        self.assertIsNone(results['userdata'])
        self.assertEqual(results['metadata'], {})

    def test_seed_dir_empty2_context(self):
        populate_context_dir(self.seed_dir, {})
        results = ds.read_context_disk_dir(self.seed_dir)

        self.assertIsNone(results['userdata'])
        self.assertEqual(results['metadata'], {})

    def test_seed_dir_broken_context(self):
        populate_dir(self.seed_dir, {'context.sh': INVALID_CONTEXT})

        self.assertRaises(ds.BrokenContextDiskDir,
                          ds.read_context_disk_dir,
                          self.seed_dir)

    def test_context_parser(self):
        populate_context_dir(self.seed_dir, TEST_VARS)
        results = ds.read_context_disk_dir(self.seed_dir)

        self.assertTrue('metadata' in results)
        self.assertEqual(TEST_VARS, results['metadata'])

    def test_ssh_key(self):
        public_keys = ['first key', 'second key']
        for c in range(4):
            for k in ('SSH_KEY', 'SSH_PUBLIC_KEY'):
                my_d = os.path.join(self.tmp, "%s-%i" % (k, c))
                populate_context_dir(my_d, {k: '\n'.join(public_keys)})
                results = ds.read_context_disk_dir(my_d)

                self.assertTrue('metadata' in results)
                self.assertTrue('public-keys' in results['metadata'])
                self.assertEqual(public_keys,
                                 results['metadata']['public-keys'])

            public_keys.append(SSH_KEY % (c + 1,))

    def test_user_data_plain(self):
        for k in ('USER_DATA', 'USERDATA'):
            my_d = os.path.join(self.tmp, k)
            populate_context_dir(my_d, {k: USER_DATA,
                                        'USERDATA_ENCODING': ''})
            results = ds.read_context_disk_dir(my_d)

            self.assertTrue('userdata' in results)
            self.assertEqual(USER_DATA, results['userdata'])

    def test_user_data_encoding_required_for_decode(self):
        b64userdata = util.b64e(USER_DATA)
        for k in ('USER_DATA', 'USERDATA'):
            my_d = os.path.join(self.tmp, k)
            populate_context_dir(my_d, {k: b64userdata})
            results = ds.read_context_disk_dir(my_d)

            self.assertTrue('userdata' in results)
            self.assertEqual(b64userdata, results['userdata'])

    def test_user_data_base64_encoding(self):
        for k in ('USER_DATA', 'USERDATA'):
            my_d = os.path.join(self.tmp, k)
            populate_context_dir(my_d, {k: util.b64e(USER_DATA),
                                        'USERDATA_ENCODING': 'base64'})
            results = ds.read_context_disk_dir(my_d)

            self.assertTrue('userdata' in results)
            self.assertEqual(USER_DATA, results['userdata'])

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_hostname(self, m_get_phys_by_mac):
        for dev in ('eth0', 'ens3'):
            m_get_phys_by_mac.return_value = {MACADDR: dev}
            for k in ('HOSTNAME', 'PUBLIC_IP', 'IP_PUBLIC', 'ETH0_IP'):
                my_d = os.path.join(self.tmp, k)
                populate_context_dir(my_d, {k: PUBLIC_IP})
                results = ds.read_context_disk_dir(my_d)

                self.assertTrue('metadata' in results)
                self.assertTrue('local-hostname' in results['metadata'])
                self.assertEqual(
                    PUBLIC_IP, results['metadata']['local-hostname'])

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_network_interfaces(self, m_get_phys_by_mac):
        for dev in ('eth0', 'ens3'):
            m_get_phys_by_mac.return_value = {MACADDR: dev}

            # without ETH0_MAC
            # for Older OpenNebula?
            populate_context_dir(self.seed_dir, {'ETH0_IP': IP_BY_MACADDR})
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP_BY_MACADDR + '/' + IP4_PREFIX in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP and ETH0_MAC
            populate_context_dir(
                self.seed_dir, {'ETH0_IP': IP_BY_MACADDR, 'ETH0_MAC': MACADDR})
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP_BY_MACADDR + '/' + IP4_PREFIX in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP with empty string and ETH0_MAC
            # in the case of using Virtual Network contains
            # "AR = [ TYPE = ETHER ]"
            populate_context_dir(
                self.seed_dir, {'ETH0_IP': '', 'ETH0_MAC': MACADDR})
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP_BY_MACADDR + '/' + IP4_PREFIX in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_MASK
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_MASK': '255.255.0.0'
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP_BY_MACADDR + '/16' in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_MASK with empty string
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_MASK': ''
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP_BY_MACADDR + '/' + IP4_PREFIX in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP6
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP6': IP6_GLOBAL,
                    'ETH0_MAC': MACADDR,
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP6_GLOBAL + '/64' in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP6_ULA
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP6_ULA': IP6_ULA,
                    'ETH0_MAC': MACADDR,
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP6_ULA + '/64' in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP6 and ETH0_IP6_PREFIX_LENGTH
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP6': IP6_GLOBAL,
                    'ETH0_IP6_PREFIX_LENGTH': IP6_PREFIX,
                    'ETH0_MAC': MACADDR,
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP6_GLOBAL + '/' + IP6_PREFIX in
                results['network-interfaces']['ethernets'][dev]['addresses'])

            # ETH0_IP6 and ETH0_IP6_PREFIX_LENGTH with empty string
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP6': IP6_GLOBAL,
                    'ETH0_IP6_PREFIX_LENGTH': '',
                    'ETH0_MAC': MACADDR,
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(
                IP6_GLOBAL + '/64' in
                results['network-interfaces']['ethernets'][dev]['addresses'])

    def test_find_candidates(self):
        def my_devs_with(criteria):
            return {
                "LABEL=CONTEXT": ["/dev/sdb"],
                "LABEL=CDROM": ["/dev/sr0"],
                "TYPE=iso9660": ["/dev/vdb"],
            }.get(criteria, [])

        orig_find_devs_with = util.find_devs_with
        try:
            util.find_devs_with = my_devs_with
            self.assertEqual(["/dev/sdb", "/dev/sr0", "/dev/vdb"],
                             ds.find_candidate_devs())
        finally:
            util.find_devs_with = orig_find_devs_with


class TestOpenNebulaNetwork(unittest.TestCase):

    system_nics = ('eth0', 'ens3')

    def test_context_devname(self):
        """Verify context_devname correctly returns mac and name."""
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH1_MAC': '02:00:0a:12:0f:0f', }
        expected = {
            '02:00:0a:12:01:01': 'ETH0',
            '02:00:0a:12:0f:0f': 'ETH1', }
        net = ds.OpenNebulaNetwork(context)
        self.assertEqual(expected, net.context_devname)

    def test_get_nameservers(self):
        """
        Verify get_nameservers('device') correctly returns DNS server addresses
        and search domains.
        """
        context = {
            'DNS': '1.2.3.8',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_SEARCH_DOMAIN': 'example.com example.org', }
        expected = {
            'addresses': ['1.2.3.6', '1.2.3.7', '1.2.3.8'],
            'search': ['example.com', 'example.org']}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_nameservers('eth0')
        self.assertEqual(expected, val)

    def test_get_mtu(self):
        """Verify get_mtu('device') correctly returns MTU size."""
        context = {'ETH0_MTU': '1280'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_mtu('eth0')
        self.assertEqual('1280', val)

    def test_get_ip(self):
        """Verify get_ip('device') correctly returns IPv4 address."""
        context = {'ETH0_IP': PUBLIC_IP}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip('eth0', MACADDR)
        self.assertEqual(PUBLIC_IP, val)

    def test_get_ip_emptystring(self):
        """
        Verify get_ip('device') correctly returns IPv4 address.
        It returns IP address created by MAC address if ETH0_IP has empty
        string.
        """
        context = {'ETH0_IP': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip('eth0', MACADDR)
        self.assertEqual(IP_BY_MACADDR, val)

    def test_get_ip6(self):
        """
        Verify get_ip6('device') correctly returns IPv6 address.
        In this case, IPv6 address is Given by ETH0_IP6.
        """
        context = {
            'ETH0_IP6': IP6_GLOBAL,
            'ETH0_IP6_ULA': '', }
        expected = [IP6_GLOBAL]
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip6('eth0')
        self.assertEqual(expected, val)

    def test_get_ip6_ula(self):
        """
        Verify get_ip6('device') correctly returns IPv6 address.
        In this case, IPv6 address is Given by ETH0_IP6_ULA.
        """
        context = {
            'ETH0_IP6': '',
            'ETH0_IP6_ULA': IP6_ULA, }
        expected = [IP6_ULA]
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip6('eth0')
        self.assertEqual(expected, val)

    def test_get_ip6_dual(self):
        """
        Verify get_ip6('device') correctly returns IPv6 address.
        In this case, IPv6 addresses are Given by ETH0_IP6 and ETH0_IP6_ULA.
        """
        context = {
            'ETH0_IP6': IP6_GLOBAL,
            'ETH0_IP6_ULA': IP6_ULA, }
        expected = [IP6_GLOBAL, IP6_ULA]
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip6('eth0')
        self.assertEqual(expected, val)

    def test_get_ip6_prefix(self):
        """
        Verify get_ip6_prefix('device') correctly returns IPv6 prefix.
        """
        context = {'ETH0_IP6_PREFIX_LENGTH': IP6_PREFIX}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip6_prefix('eth0')
        self.assertEqual(IP6_PREFIX, val)

    def test_get_ip6_prefix_emptystring(self):
        """
        Verify get_ip6_prefix('device') correctly returns IPv6 prefix.
        It returns default value '64' if ETH0_IP6_PREFIX_LENGTH has empty
        string.
        """
        context = {'ETH0_IP6_PREFIX_LENGTH': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_ip6_prefix('eth0')
        self.assertEqual('64', val)

    def test_get_gateway(self):
        """
        Verify get_gateway('device') correctly returns IPv4 default gateway
        address.
        """
        context = {'ETH0_GATEWAY': '1.2.3.5'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_gateway('eth0')
        self.assertEqual('1.2.3.5', val)

    def test_get_gateway6(self):
        """
        Verify get_gateway6('device') correctly returns IPv6 default gateway
        address.
        """
        context = {'ETH0_GATEWAY6': IP6_GW}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_gateway6('eth0')
        self.assertEqual(IP6_GW, val)

    def test_get_mask(self):
        """
        Verify get_mask('device') correctly returns IPv4 subnet mask.
        """
        context = {'ETH0_MASK': '255.255.0.0'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_mask('eth0')
        self.assertEqual('255.255.0.0', val)

    def test_get_mask_emptystring(self):
        """
        Verify get_mask('device') correctly returns IPv4 subnet mask.
        It returns default value '255.255.255.0' if ETH0_MASK has empty string.
        """
        context = {'ETH0_MASK': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_mask('eth0')
        self.assertEqual('255.255.255.0', val)

    def test_get_network(self):
        """
        Verify get_network('device') correctly returns IPv4 network address.
        """
        context = {'ETH0_NETWORK': '1.2.3.0'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_network('eth0', MACADDR)
        self.assertEqual('1.2.3.0', val)

    def test_get_network_emptystring(self):
        """
        Verify get_network('device') correctly returns IPv4 network address.
        It returns network address created by MAC address if ETH0_NETWORK has
        empty string.
        """
        context = {'ETH0_NETWORK': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_network('eth0', MACADDR)
        self.assertEqual('10.18.1.0', val)

    def test_get_field(self):
        """
        Verify get_field('device', 'name') returns *context* value.
        """
        context = {'ETH9_DUMMY': 'DUMMY_VALUE'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_field('eth9', 'dummy')
        self.assertEqual('DUMMY_VALUE', val)

    def test_get_field_withdefaultvalue(self):
        """
        Verify get_field('device', 'name', 'default value') returns *context*
        value.
        """
        context = {'ETH9_DUMMY': 'DUMMY_VALUE'}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_field('eth9', 'dummy', 'DEFAULT_VALUE')
        self.assertEqual('DUMMY_VALUE', val)

    def test_get_field_withdefaultvalue_emptycontext(self):
        """
        Verify get_field('device', 'name', 'default value') returns *default*
        value if context value is empty string.
        """
        context = {'ETH9_DUMMY': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_field('eth9', 'dummy', 'DEFAULT_VALUE')
        self.assertEqual('DEFAULT_VALUE', val)

    def test_get_field_emptycontext(self):
        """
        Verify get_field('device', 'name') returns None if context value is
        empty string.
        """
        context = {'ETH9_DUMMY': ''}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_field('eth9', 'dummy')
        self.assertEqual(None, val)

    def test_get_field_nonecontext(self):
        """
        Verify get_field('device', 'name') returns None if context value is
        None.
        """
        context = {'ETH9_DUMMY': None}
        net = ds.OpenNebulaNetwork(context)
        val = net.get_field('eth9', 'dummy')
        self.assertEqual(None, val)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_gen_conf_gateway(self, m_get_phys_by_mac):
        """Test rendering with/without IPv4 gateway"""
        self.maxDiff = None
        # empty ETH0_GATEWAY
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_GATEWAY': '', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

        # set ETH0_GATEWAY
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_GATEWAY': '1.2.3.5', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'gateway4': '1.2.3.5',
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_gen_conf_gateway6(self, m_get_phys_by_mac):
        """Test rendering with/without IPv6 gateway"""
        self.maxDiff = None
        # empty ETH0_GATEWAY6
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_GATEWAY6': '', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

        # set ETH0_GATEWAY6
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_GATEWAY6': IP6_GW, }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'gateway6': IP6_GW,
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_gen_conf_ipv6address(self, m_get_phys_by_mac):
        """Test rendering with/without IPv6 address"""
        self.maxDiff = None
        # empty ETH0_IP6, ETH0_IP6_ULA, ETH0_IP6_PREFIX_LENGTH
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_IP6': '',
            'ETH0_IP6_ULA': '',
            'ETH0_IP6_PREFIX_LENGTH': '', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

        # set ETH0_IP6, ETH0_IP6_ULA, ETH0_IP6_PREFIX_LENGTH
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_IP6': IP6_GLOBAL,
            'ETH0_IP6_PREFIX_LENGTH': IP6_PREFIX,
            'ETH0_IP6_ULA': IP6_ULA, }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [
                            IP_BY_MACADDR + '/' + IP4_PREFIX,
                            IP6_GLOBAL + '/' + IP6_PREFIX,
                            IP6_ULA + '/' + IP6_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_gen_conf_dns(self, m_get_phys_by_mac):
        """Test rendering with/without DNS server, search domain"""
        self.maxDiff = None
        # empty DNS, ETH0_DNS, ETH0_SEARCH_DOMAIN
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'DNS': '',
            'ETH0_DNS': '',
            'ETH0_SEARCH_DOMAIN': '', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

        # set DNS, ETH0_DNS, ETH0_SEARCH_DOMAIN
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'DNS': '1.2.3.8',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_SEARCH_DOMAIN': 'example.com example.org', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'nameservers': {
                            'addresses': ['1.2.3.6', '1.2.3.7', '1.2.3.8'],
                            'search': ['example.com', 'example.org']},
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_gen_conf_mtu(self, m_get_phys_by_mac):
        """Test rendering with/without MTU"""
        self.maxDiff = None
        # empty ETH0_MTU
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_MTU': '', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

        # set ETH0_MTU
        context = {
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_MTU': '1280', }
        for nic in self.system_nics:
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'mtu': '1280',
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork(context)
            self.assertEqual(net.gen_conf(), expected)

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_eth0(self, m_get_phys_by_mac):
        for nic in self.system_nics:
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork({})
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/' + IP4_PREFIX]}}}

            self.assertEqual(net.gen_conf(), expected)

    def test_eth0_override(self):
        self.maxDiff = None
        context = {
            'DNS': '1.2.3.8',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_GATEWAY': '1.2.3.5',
            'ETH0_GATEWAY6': '',
            'ETH0_IP': IP_BY_MACADDR,
            'ETH0_IP6': '',
            'ETH0_IP6_PREFIX_LENGTH': '',
            'ETH0_IP6_ULA': '',
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_MASK': '255.255.0.0',
            'ETH0_MTU': '',
            'ETH0_NETWORK': '10.18.0.0',
            'ETH0_SEARCH_DOMAIN': '',
        }
        for nic in self.system_nics:
            net = ds.OpenNebulaNetwork(context,
                                       system_nics_by_mac={MACADDR: nic})
            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [IP_BY_MACADDR + '/16'],
                        'gateway4': '1.2.3.5',
                        'nameservers': {
                            'addresses': ['1.2.3.6', '1.2.3.7', '1.2.3.8']}}}}

            self.assertEqual(expected, net.gen_conf())

    def test_eth0_v4v6_override(self):
        self.maxDiff = None
        context = {
            'DNS': '1.2.3.8',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_GATEWAY': '1.2.3.5',
            'ETH0_GATEWAY6': IP6_GW,
            'ETH0_IP': IP_BY_MACADDR,
            'ETH0_IP6': IP6_GLOBAL,
            'ETH0_IP6_PREFIX_LENGTH': IP6_PREFIX,
            'ETH0_IP6_ULA': IP6_ULA,
            'ETH0_MAC': '02:00:0a:12:01:01',
            'ETH0_MASK': '255.255.0.0',
            'ETH0_MTU': '1280',
            'ETH0_NETWORK': '10.18.0.0',
            'ETH0_SEARCH_DOMAIN': 'example.com example.org',
        }
        for nic in self.system_nics:
            net = ds.OpenNebulaNetwork(context,
                                       system_nics_by_mac={MACADDR: nic})

            expected = {
                'version': 2,
                'ethernets': {
                    nic: {
                        'match': {'macaddress': MACADDR},
                        'addresses': [
                            IP_BY_MACADDR + '/16',
                            IP6_GLOBAL + '/' + IP6_PREFIX,
                            IP6_ULA + '/' + IP6_PREFIX],
                        'gateway4': '1.2.3.5',
                        'gateway6': IP6_GW,
                        'nameservers': {
                            'addresses': ['1.2.3.6', '1.2.3.7', '1.2.3.8'],
                            'search': ['example.com', 'example.org']},
                        'mtu': '1280'}}}

            self.assertEqual(expected, net.gen_conf())

    def test_multiple_nics(self):
        """Test rendering multiple nics with names that differ from context."""
        self.maxDiff = None
        MAC_1 = "02:00:0a:12:01:01"
        MAC_2 = "02:00:0a:12:01:02"
        context = {
            'DNS': '1.2.3.8',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_GATEWAY': '1.2.3.5',
            'ETH0_GATEWAY6': IP6_GW,
            'ETH0_IP': '10.18.1.1',
            'ETH0_IP6': IP6_GLOBAL,
            'ETH0_IP6_PREFIX_LENGTH': '',
            'ETH0_IP6_ULA': IP6_ULA,
            'ETH0_MAC': MAC_2,
            'ETH0_MASK': '255.255.0.0',
            'ETH0_MTU': '1280',
            'ETH0_NETWORK': '10.18.0.0',
            'ETH0_SEARCH_DOMAIN': 'example.com',
            'ETH3_DNS': '10.3.1.2',
            'ETH3_GATEWAY': '10.3.0.1',
            'ETH3_GATEWAY6': '',
            'ETH3_IP': '10.3.1.3',
            'ETH3_IP6': '',
            'ETH3_IP6_PREFIX_LENGTH': '',
            'ETH3_IP6_ULA': '',
            'ETH3_MAC': MAC_1,
            'ETH3_MASK': '255.255.0.0',
            'ETH3_MTU': '',
            'ETH3_NETWORK': '10.3.0.0',
            'ETH3_SEARCH_DOMAIN': 'third.example.com third.example.org',
        }
        net = ds.OpenNebulaNetwork(
            context, system_nics_by_mac={MAC_1: 'enp0s25', MAC_2: 'enp1s2'})

        expected = {
            'version': 2,
            'ethernets': {
                'enp1s2': {
                    'match': {'macaddress': MAC_2},
                    'addresses': [
                        '10.18.1.1/16',
                        IP6_GLOBAL + '/64',
                        IP6_ULA + '/64'],
                    'gateway4': '1.2.3.5',
                    'gateway6': IP6_GW,
                    'nameservers': {
                        'addresses': ['1.2.3.6', '1.2.3.7', '1.2.3.8'],
                        'search': ['example.com']},
                    'mtu': '1280'},
                'enp0s25': {
                    'match': {'macaddress': MAC_1},
                    'addresses': ['10.3.1.3/16'],
                    'gateway4': '10.3.0.1',
                    'nameservers': {
                        'addresses': ['10.3.1.2', '1.2.3.8'],
                        'search': [
                            'third.example.com',
                            'third.example.org']}}}}

        self.assertEqual(expected, net.gen_conf())


class TestParseShellConfig(unittest.TestCase):
    def test_no_seconds(self):
        cfg = '\n'.join(["foo=bar", "SECONDS=2", "xx=foo"])
        # we could test 'sleep 2', but that would make the test run slower.
        ret = ds.parse_shell_config(cfg)
        self.assertEqual(ret, {"foo": "bar", "xx": "foo"})


def populate_context_dir(path, variables):
    data = "# Context variables generated by OpenNebula\n"
    for k, v in variables.items():
        data += ("%s='%s'\n" % (k.upper(), v.replace(r"'", r"'\''")))
    populate_dir(path, {'context.sh': data})

# vi: ts=4 expandtab
