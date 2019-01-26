# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2016 VMware INC.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#         Pengpeng Sun <pengpengs@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import sys
import tempfile
import textwrap

from cloudinit.sources.DataSourceOVF import get_network_config_from_conf
from cloudinit.sources.DataSourceOVF import read_vmware_imc
from cloudinit.sources.helpers.vmware.imc.boot_proto import BootProtoEnum
from cloudinit.sources.helpers.vmware.imc.config import Config
from cloudinit.sources.helpers.vmware.imc.config_file import ConfigFile
from cloudinit.sources.helpers.vmware.imc.config_nic import gen_subnet
from cloudinit.sources.helpers.vmware.imc.config_nic import NicConfigurator
from cloudinit.tests.helpers import CiTestCase

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger(__name__)


class TestVmwareConfigFile(CiTestCase):

    def test_utility_methods(self):
        """Tests basic utility methods of ConfigFile class"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        cf.clear()

        self.assertEqual(0, len(cf), "clear size")

        cf._insertKey("  PASSWORD|-PASS ", "  foo  ")
        cf._insertKey("BAR", "   ")

        self.assertEqual(2, len(cf), "insert size")
        self.assertEqual('foo', cf["PASSWORD|-PASS"], "password")
        self.assertTrue("PASSWORD|-PASS" in cf, "hasPassword")
        self.assertFalse(cf.should_keep_current_value("PASSWORD|-PASS"),
                         "keepPassword")
        self.assertFalse(cf.should_remove_current_value("PASSWORD|-PASS"),
                         "removePassword")
        self.assertFalse("FOO" in cf, "hasFoo")
        self.assertTrue(cf.should_keep_current_value("FOO"), "keepFoo")
        self.assertFalse(cf.should_remove_current_value("FOO"), "removeFoo")
        self.assertTrue("BAR" in cf, "hasBar")
        self.assertFalse(cf.should_keep_current_value("BAR"), "keepBar")
        self.assertTrue(cf.should_remove_current_value("BAR"), "removeBar")

    def test_datasource_instance_id(self):
        """Tests instance id for the DatasourceOVF"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        instance_id_prefix = 'iid-vmware-'

        conf = Config(cf)

        (md1, _, _) = read_vmware_imc(conf)
        self.assertIn(instance_id_prefix, md1["instance-id"])
        self.assertEqual(len(md1["instance-id"]), len(instance_id_prefix) + 8)

        (md2, _, _) = read_vmware_imc(conf)
        self.assertIn(instance_id_prefix, md2["instance-id"])
        self.assertEqual(len(md2["instance-id"]), len(instance_id_prefix) + 8)

        self.assertNotEqual(md1["instance-id"], md2["instance-id"])

    def test_configfile_static_2nics(self):
        """Tests Config class for a configuration with two static NICs."""
        cf = ConfigFile("tests/data/vmware/cust-static-2nic.cfg")

        conf = Config(cf)

        self.assertEqual('myhost1', conf.host_name, "hostName")
        self.assertEqual('Africa/Abidjan', conf.timezone, "tz")
        self.assertTrue(conf.utc, "utc")

        self.assertEqual(['10.20.145.1', '10.20.145.2'],
                         conf.name_servers,
                         "dns")
        self.assertEqual(['eng.vmware.com', 'proxy.vmware.com'],
                         conf.dns_suffixes,
                         "suffixes")

        nics = conf.nics
        ipv40 = nics[0].staticIpv4

        self.assertEqual(2, len(nics), "nics")
        self.assertEqual('NIC1', nics[0].name, "nic0")
        self.assertEqual('00:50:56:a6:8c:08', nics[0].mac, "mac0")
        self.assertEqual(BootProtoEnum.STATIC, nics[0].bootProto, "bootproto0")
        self.assertEqual('10.20.87.154', ipv40[0].ip, "ipv4Addr0")
        self.assertEqual('255.255.252.0', ipv40[0].netmask, "ipv4Mask0")
        self.assertEqual(2, len(ipv40[0].gateways), "ipv4Gw0")
        self.assertEqual('10.20.87.253', ipv40[0].gateways[0], "ipv4Gw0_0")
        self.assertEqual('10.20.87.105', ipv40[0].gateways[1], "ipv4Gw0_1")

        self.assertEqual(1, len(nics[0].staticIpv6), "ipv6Cnt0")
        self.assertEqual('fc00:10:20:87::154',
                         nics[0].staticIpv6[0].ip,
                         "ipv6Addr0")

        self.assertEqual('NIC2', nics[1].name, "nic1")
        self.assertTrue(not nics[1].staticIpv6, "ipv61 dhcp")

    def test_config_file_dhcp_2nics(self):
        """Tests Config class for a configuration with two DHCP NICs."""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        conf = Config(cf)
        nics = conf.nics
        self.assertEqual(2, len(nics), "nics")
        self.assertEqual('NIC1', nics[0].name, "nic0")
        self.assertEqual('00:50:56:a6:8c:08', nics[0].mac, "mac0")
        self.assertEqual(BootProtoEnum.DHCP, nics[0].bootProto, "bootproto0")

    def test_config_password(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        cf._insertKey("PASSWORD|-PASS", "test-password")
        cf._insertKey("PASSWORD|RESET", "no")

        conf = Config(cf)
        self.assertEqual('test-password', conf.admin_password, "password")
        self.assertFalse(conf.reset_password, "do not reset password")

    def test_config_reset_passwd(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        cf._insertKey("PASSWORD|-PASS", "test-password")
        cf._insertKey("PASSWORD|RESET", "random")

        conf = Config(cf)
        with self.assertRaises(ValueError):
            pw = conf.reset_password
            self.assertIsNone(pw)

        cf.clear()
        cf._insertKey("PASSWORD|RESET", "yes")
        self.assertEqual(1, len(cf), "insert size")

        conf = Config(cf)
        self.assertTrue(conf.reset_password, "reset password")

    def test_get_config_nameservers(self):
        """Tests DNS and nameserver settings in a configuration."""
        cf = ConfigFile("tests/data/vmware/cust-static-2nic.cfg")

        config = Config(cf)

        network_config = get_network_config_from_conf(config, False)

        self.assertEqual(1, network_config.get('version'))

        config_types = network_config.get('config')
        name_servers = None
        dns_suffixes = None

        for type in config_types:
            if type.get('type') == 'nameserver':
                name_servers = type.get('address')
                dns_suffixes = type.get('search')
                break

        self.assertEqual(['10.20.145.1', '10.20.145.2'],
                         name_servers,
                         "dns")
        self.assertEqual(['eng.vmware.com', 'proxy.vmware.com'],
                         dns_suffixes,
                         "suffixes")

    def test_gen_subnet(self):
        """Tests if gen_subnet properly calculates network subnet from
           IPv4 address and netmask"""
        ip_subnet_list = [['10.20.87.253', '255.255.252.0', '10.20.84.0'],
                          ['10.20.92.105', '255.255.252.0', '10.20.92.0'],
                          ['192.168.0.10', '255.255.0.0', '192.168.0.0']]
        for entry in ip_subnet_list:
            self.assertEqual(entry[2], gen_subnet(entry[0], entry[1]),
                             "Subnet for a specified ip and netmask")

    def test_get_config_dns_suffixes(self):
        """Tests if get_network_config_from_conf properly
           generates nameservers and dns settings from a
           specified configuration"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        config = Config(cf)

        network_config = get_network_config_from_conf(config, False)

        self.assertEqual(1, network_config.get('version'))

        config_types = network_config.get('config')
        name_servers = None
        dns_suffixes = None

        for type in config_types:
            if type.get('type') == 'nameserver':
                name_servers = type.get('address')
                dns_suffixes = type.get('search')
                break

        self.assertEqual([],
                         name_servers,
                         "dns")
        self.assertEqual(['eng.vmware.com'],
                         dns_suffixes,
                         "suffixes")

    def test_get_nics_list_dhcp(self):
        """Tests if NicConfigurator properly calculates network subnets
           for a configuration with a list of DHCP NICs"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        config = Config(cf)

        nicConfigurator = NicConfigurator(config.nics, False)
        nics_cfg_list = nicConfigurator.generate()

        self.assertEqual(2, len(nics_cfg_list), "number of config elements")

        nic1 = {'name': 'NIC1'}
        nic2 = {'name': 'NIC2'}
        for cfg in nics_cfg_list:
            if cfg.get('name') == nic1.get('name'):
                nic1.update(cfg)
            elif cfg.get('name') == nic2.get('name'):
                nic2.update(cfg)

        self.assertEqual('physical', nic1.get('type'), 'type of NIC1')
        self.assertEqual('NIC1', nic1.get('name'), 'name of NIC1')
        self.assertEqual('00:50:56:a6:8c:08', nic1.get('mac_address'),
                         'mac address of NIC1')
        subnets = nic1.get('subnets')
        self.assertEqual(1, len(subnets), 'number of subnets for NIC1')
        subnet = subnets[0]
        self.assertEqual('dhcp', subnet.get('type'), 'DHCP type for NIC1')
        self.assertEqual('auto', subnet.get('control'), 'NIC1 Control type')

        self.assertEqual('physical', nic2.get('type'), 'type of NIC2')
        self.assertEqual('NIC2', nic2.get('name'), 'name of NIC2')
        self.assertEqual('00:50:56:a6:5a:de', nic2.get('mac_address'),
                         'mac address of NIC2')
        subnets = nic2.get('subnets')
        self.assertEqual(1, len(subnets), 'number of subnets for NIC2')
        subnet = subnets[0]
        self.assertEqual('dhcp', subnet.get('type'), 'DHCP type for NIC2')
        self.assertEqual('auto', subnet.get('control'), 'NIC2 Control type')

    def test_get_nics_list_static(self):
        """Tests if NicConfigurator properly calculates network subnets
           for a configuration with 2 static NICs"""
        cf = ConfigFile("tests/data/vmware/cust-static-2nic.cfg")

        config = Config(cf)

        nicConfigurator = NicConfigurator(config.nics, False)
        nics_cfg_list = nicConfigurator.generate()

        self.assertEqual(2, len(nics_cfg_list), "number of elements")

        nic1 = {'name': 'NIC1'}
        nic2 = {'name': 'NIC2'}
        route_list = []
        for cfg in nics_cfg_list:
            cfg_type = cfg.get('type')
            if cfg_type == 'physical':
                if cfg.get('name') == nic1.get('name'):
                    nic1.update(cfg)
                elif cfg.get('name') == nic2.get('name'):
                    nic2.update(cfg)

        self.assertEqual('physical', nic1.get('type'), 'type of NIC1')
        self.assertEqual('NIC1', nic1.get('name'), 'name of NIC1')
        self.assertEqual('00:50:56:a6:8c:08', nic1.get('mac_address'),
                         'mac address of NIC1')

        subnets = nic1.get('subnets')
        self.assertEqual(2, len(subnets), 'Number of subnets')

        static_subnet = []
        static6_subnet = []

        for subnet in subnets:
            subnet_type = subnet.get('type')
            if subnet_type == 'static':
                static_subnet.append(subnet)
            elif subnet_type == 'static6':
                static6_subnet.append(subnet)
            else:
                self.assertEqual(True, False, 'Unknown type')
            if 'route' in subnet:
                for route in subnet.get('routes'):
                    route_list.append(route)

        self.assertEqual(1, len(static_subnet), 'Number of static subnet')
        self.assertEqual(1, len(static6_subnet), 'Number of static6 subnet')

        subnet = static_subnet[0]
        self.assertEqual('10.20.87.154', subnet.get('address'),
                         'IPv4 address of static subnet')
        self.assertEqual('255.255.252.0', subnet.get('netmask'),
                         'NetMask of static subnet')
        self.assertEqual('auto', subnet.get('control'),
                         'control for static subnet')

        subnet = static6_subnet[0]
        self.assertEqual('fc00:10:20:87::154', subnet.get('address'),
                         'IPv6 address of static subnet')
        self.assertEqual('64', subnet.get('netmask'),
                         'NetMask of static6 subnet')

        route_set = set(['10.20.87.253', '10.20.87.105', '192.168.0.10'])
        for route in route_list:
            self.assertEqual(10000, route.get('metric'), 'metric of route')
            gateway = route.get('gateway')
            if gateway in route_set:
                route_set.discard(gateway)
            else:
                self.assertEqual(True, False, 'invalid gateway %s' % (gateway))

        self.assertEqual('physical', nic2.get('type'), 'type of NIC2')
        self.assertEqual('NIC2', nic2.get('name'), 'name of NIC2')
        self.assertEqual('00:50:56:a6:ef:7d', nic2.get('mac_address'),
                         'mac address of NIC2')

        subnets = nic2.get('subnets')
        self.assertEqual(1, len(subnets), 'Number of subnets for NIC2')

        subnet = subnets[0]
        self.assertEqual('static', subnet.get('type'), 'Subnet type')
        self.assertEqual('192.168.6.102', subnet.get('address'),
                         'Subnet address')
        self.assertEqual('255.255.0.0', subnet.get('netmask'),
                         'Subnet netmask')

    def test_custom_script(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertIsNone(conf.custom_script_name)
        cf._insertKey("CUSTOM-SCRIPT|SCRIPT-NAME", "test-script")
        conf = Config(cf)
        self.assertEqual("test-script", conf.custom_script_name)


class TestVmwareNetConfig(CiTestCase):
    """Test conversion of vmware config to cloud-init config."""

    maxDiff = None

    def _get_NicConfigurator(self, text):
        fp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.tmp_dir(),
                                             delete=False) as fp:
                fp.write(text)
                fp.close()
            cfg = Config(ConfigFile(fp.name))
            return NicConfigurator(cfg.nics, use_system_devices=False)
        finally:
            if fp:
                os.unlink(fp.name)

    def test_non_primary_nic_without_gateway(self):
        """A non primary nic set is not required to have a gateway."""
        config = textwrap.dedent("""\
            [NETWORK]
            NETWORKING = yes
            BOOTPROTO = dhcp
            HOSTNAME = myhost1
            DOMAINNAME = eng.vmware.com

            [NIC-CONFIG]
            NICS = NIC1

            [NIC1]
            MACADDR = 00:50:56:a6:8c:08
            ONBOOT = yes
            IPv4_MODE = BACKWARDS_COMPATIBLE
            BOOTPROTO = static
            IPADDR = 10.20.87.154
            NETMASK = 255.255.252.0
            """)
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            [{'type': 'physical', 'name': 'NIC1',
              'mac_address': '00:50:56:a6:8c:08',
              'subnets': [
                  {'control': 'auto', 'type': 'static',
                   'address': '10.20.87.154', 'netmask': '255.255.252.0'}]}],
            nc.generate())

    def test_non_primary_nic_with_gateway(self):
        """A non primary nic set can have a gateway."""
        config = textwrap.dedent("""\
            [NETWORK]
            NETWORKING = yes
            BOOTPROTO = dhcp
            HOSTNAME = myhost1
            DOMAINNAME = eng.vmware.com

            [NIC-CONFIG]
            NICS = NIC1

            [NIC1]
            MACADDR = 00:50:56:a6:8c:08
            ONBOOT = yes
            IPv4_MODE = BACKWARDS_COMPATIBLE
            BOOTPROTO = static
            IPADDR = 10.20.87.154
            NETMASK = 255.255.252.0
            GATEWAY = 10.20.87.253
            """)
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            [{'type': 'physical', 'name': 'NIC1',
              'mac_address': '00:50:56:a6:8c:08',
              'subnets': [
                  {'control': 'auto', 'type': 'static',
                   'address': '10.20.87.154', 'netmask': '255.255.252.0',
                   'routes':
                       [{'type': 'route', 'destination': '10.20.84.0/22',
                         'gateway': '10.20.87.253', 'metric': 10000}]}]}],
            nc.generate())

    def test_cust_non_primary_nic_with_gateway_(self):
        """A customer non primary nic set can have a gateway."""
        config = textwrap.dedent("""\
            [NETWORK]
            NETWORKING = yes
            BOOTPROTO = dhcp
            HOSTNAME = static-debug-vm
            DOMAINNAME = cluster.local

            [NIC-CONFIG]
            NICS = NIC1

            [NIC1]
            MACADDR = 00:50:56:ac:d1:8a
            ONBOOT = yes
            IPv4_MODE = BACKWARDS_COMPATIBLE
            BOOTPROTO = static
            IPADDR = 100.115.223.75
            NETMASK = 255.255.255.0
            GATEWAY = 100.115.223.254


            [DNS]
            DNSFROMDHCP=no

            NAMESERVER|1 = 8.8.8.8

            [DATETIME]
            UTC = yes
            """)
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            [{'type': 'physical', 'name': 'NIC1',
              'mac_address': '00:50:56:ac:d1:8a',
              'subnets': [
                  {'control': 'auto', 'type': 'static',
                   'address': '100.115.223.75', 'netmask': '255.255.255.0',
                   'routes':
                       [{'type': 'route', 'destination': '100.115.223.0/24',
                         'gateway': '100.115.223.254', 'metric': 10000}]}]}],
            nc.generate())

    def test_a_primary_nic_with_gateway(self):
        """A primary nic set can have a gateway."""
        config = textwrap.dedent("""\
            [NETWORK]
            NETWORKING = yes
            BOOTPROTO = dhcp
            HOSTNAME = myhost1
            DOMAINNAME = eng.vmware.com

            [NIC-CONFIG]
            NICS = NIC1

            [NIC1]
            MACADDR = 00:50:56:a6:8c:08
            ONBOOT = yes
            IPv4_MODE = BACKWARDS_COMPATIBLE
            BOOTPROTO = static
            IPADDR = 10.20.87.154
            NETMASK = 255.255.252.0
            PRIMARY = true
            GATEWAY = 10.20.87.253
            """)
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            [{'type': 'physical', 'name': 'NIC1',
              'mac_address': '00:50:56:a6:8c:08',
              'subnets': [
                  {'control': 'auto', 'type': 'static',
                   'address': '10.20.87.154', 'netmask': '255.255.252.0',
                   'gateway': '10.20.87.253'}]}],
            nc.generate())


# vi: ts=4 expandtab
