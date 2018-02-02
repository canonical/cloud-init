# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import helpers
from cloudinit.sources import DataSourceOpenNebula as ds
from cloudinit import util
from cloudinit.tests.helpers import mock, populate_dir, CiTestCase
from textwrap import dedent

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

DS_PATH = "cloudinit.sources.DataSourceOpenNebula"


class TestOpenNebulaDataSource(CiTestCase):
    parsed_user = None

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
            self.assertTrue(IP_BY_MACADDR in results['network-interfaces'])

            # ETH0_IP and ETH0_MAC
            populate_context_dir(
                self.seed_dir, {'ETH0_IP': IP_BY_MACADDR, 'ETH0_MAC': MACADDR})
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(IP_BY_MACADDR in results['network-interfaces'])

            # ETH0_IP with empty string and ETH0_MAC
            # in the case of using Virtual Network contains
            # "AR = [ TYPE = ETHER ]"
            populate_context_dir(
                self.seed_dir, {'ETH0_IP': '', 'ETH0_MAC': MACADDR})
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue(IP_BY_MACADDR in results['network-interfaces'])

            # ETH0_NETWORK
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_NETWORK': '10.18.0.0'
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue('10.18.0.0' in results['network-interfaces'])

            # ETH0_NETWORK with empty string
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_NETWORK': ''
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue('10.18.1.0' in results['network-interfaces'])

            # ETH0_MASK
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_MASK': '255.255.0.0'
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue('255.255.0.0' in results['network-interfaces'])

            # ETH0_MASK with empty string
            populate_context_dir(
                self.seed_dir, {
                    'ETH0_IP': IP_BY_MACADDR,
                    'ETH0_MAC': MACADDR,
                    'ETH0_MASK': ''
                })
            results = ds.read_context_disk_dir(self.seed_dir)

            self.assertTrue('network-interfaces' in results)
            self.assertTrue('255.255.255.0' in results['network-interfaces'])

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

    def test_lo(self):
        net = ds.OpenNebulaNetwork(context={}, system_nics_by_mac={})
        self.assertEqual(net.gen_conf(), u'''\
auto lo
iface lo inet loopback
''')

    @mock.patch(DS_PATH + ".get_physical_nics_by_mac")
    def test_eth0(self, m_get_phys_by_mac):
        for nic in self.system_nics:
            m_get_phys_by_mac.return_value = {MACADDR: nic}
            net = ds.OpenNebulaNetwork({})
            self.assertEqual(net.gen_conf(), dedent("""\
                auto lo
                iface lo inet loopback

                auto {dev}
                iface {dev} inet static
                  #hwaddress {macaddr}
                  address 10.18.1.1
                  network 10.18.1.0
                  netmask 255.255.255.0
                """.format(dev=nic, macaddr=MACADDR)))

    def test_eth0_override(self):
        context = {
            'DNS': '1.2.3.8',
            'ETH0_IP': '10.18.1.1',
            'ETH0_NETWORK': '10.18.0.0',
            'ETH0_MASK': '255.255.0.0',
            'ETH0_GATEWAY': '1.2.3.5',
            'ETH0_DOMAIN': 'example.com',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_MAC': '02:00:0a:12:01:01'
        }
        for nic in self.system_nics:
            expected = dedent("""\
                auto lo
                iface lo inet loopback

                auto {dev}
                iface {dev} inet static
                  #hwaddress {macaddr}
                  address 10.18.1.1
                  network 10.18.0.0
                  netmask 255.255.0.0
                  gateway 1.2.3.5
                  dns-search example.com
                  dns-nameservers 1.2.3.8 1.2.3.6 1.2.3.7
                  """).format(dev=nic, macaddr=MACADDR)
            net = ds.OpenNebulaNetwork(context,
                                       system_nics_by_mac={MACADDR: nic})
            self.assertEqual(expected, net.gen_conf())

    def test_multiple_nics(self):
        """Test rendering multiple nics with names that differ from context."""
        MAC_1 = "02:00:0a:12:01:01"
        MAC_2 = "02:00:0a:12:01:02"
        context = {
            'DNS': '1.2.3.8',
            'ETH0_IP': '10.18.1.1',
            'ETH0_NETWORK': '10.18.0.0',
            'ETH0_MASK': '255.255.0.0',
            'ETH0_GATEWAY': '1.2.3.5',
            'ETH0_DOMAIN': 'example.com',
            'ETH0_DNS': '1.2.3.6 1.2.3.7',
            'ETH0_MAC': MAC_2,
            'ETH3_IP': '10.3.1.3',
            'ETH3_NETWORK': '10.3.0.0',
            'ETH3_MASK': '255.255.0.0',
            'ETH3_GATEWAY': '10.3.0.1',
            'ETH3_DOMAIN': 'third.example.com',
            'ETH3_DNS': '10.3.1.2',
            'ETH3_MAC': MAC_1,
        }
        net = ds.OpenNebulaNetwork(
            context, system_nics_by_mac={MAC_1: 'enp0s25', MAC_2: 'enp1s2'})

        expected = dedent("""\
            auto lo
            iface lo inet loopback

            auto enp0s25
            iface enp0s25 inet static
              #hwaddress 02:00:0a:12:01:01
              address 10.3.1.3
              network 10.3.0.0
              netmask 255.255.0.0
              gateway 10.3.0.1
              dns-search third.example.com
              dns-nameservers 1.2.3.8 10.3.1.2

            auto enp1s2
            iface enp1s2 inet static
              #hwaddress 02:00:0a:12:01:02
              address 10.18.1.1
              network 10.18.0.0
              netmask 255.255.0.0
              gateway 1.2.3.5
              dns-search example.com
              dns-nameservers 1.2.3.8 1.2.3.6 1.2.3.7
            """)

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
