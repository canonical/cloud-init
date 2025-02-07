# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2006-2024 Broadcom. All Rights Reserved.
# Broadcom Confidential. The term "Broadcom" refers to Broadcom Inc.
# and/or its subsidiaries.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#         Pengpeng Sun <pengpeng.sun@broadcom.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import sys
import tempfile
import textwrap

from cloudinit.sources.helpers.vmware.imc.boot_proto import BootProtoEnum
from cloudinit.sources.helpers.vmware.imc.config import Config
from cloudinit.sources.helpers.vmware.imc.config_file import (
    ConfigFile as WrappedConfigFile,
)
from cloudinit.sources.helpers.vmware.imc.config_nic import NicConfigurator
from cloudinit.sources.helpers.vmware.imc.guestcust_util import (
    get_network_data_from_vmware_cust_cfg,
    get_non_network_data_from_vmware_cust_cfg,
)
from tests.helpers import cloud_init_project_dir
from tests.unittests.helpers import CiTestCase

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger(__name__)


def ConfigFile(path: str):
    return WrappedConfigFile(cloud_init_project_dir(path))


class TestVmwareConfigFile(CiTestCase):
    def test_utility_methods(self):
        """Tests basic utility methods of ConfigFile class"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        cf.clear()

        self.assertEqual(0, len(cf), "clear size")

        cf._insertKey("  PASSWORD|-PASS ", "  foo  ")
        cf._insertKey("BAR", "   ")

        self.assertEqual(2, len(cf), "insert size")
        self.assertEqual("foo", cf["PASSWORD|-PASS"], "password")
        self.assertTrue("PASSWORD|-PASS" in cf, "hasPassword")
        self.assertFalse("FOO" in cf, "hasFoo")
        self.assertTrue("BAR" in cf, "hasBar")

    def test_configfile_without_instance_id(self):
        """
        Tests instance id is None when configuration file has no instance id
        """
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)

        (md1, _) = get_non_network_data_from_vmware_cust_cfg(conf)
        self.assertFalse("instance-id" in md1)

        (md2, _) = get_non_network_data_from_vmware_cust_cfg(conf)
        self.assertFalse("instance-id" in md2)

    def test_configfile_with_instance_id(self):
        """Tests instance id get from configuration file"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic-instance-id.cfg")
        conf = Config(cf)

        (md1, _) = get_non_network_data_from_vmware_cust_cfg(conf)
        self.assertEqual(md1["instance-id"], conf.instance_id, "instance-id")

        (md2, _) = get_non_network_data_from_vmware_cust_cfg(conf)
        self.assertEqual(md2["instance-id"], conf.instance_id, "instance-id")

    def test_configfile_static_2nics(self):
        """Tests Config class for a configuration with two static NICs."""
        cf = ConfigFile("tests/data/vmware/cust-static-2nic.cfg")

        conf = Config(cf)

        self.assertEqual("myhost1", conf.host_name, "hostName")
        self.assertEqual("Africa/Abidjan", conf.timezone, "tz")

        self.assertEqual(
            ["10.20.145.1", "10.20.145.2"], conf.name_servers, "dns"
        )
        self.assertEqual(
            ["eng.vmware.com", "proxy.vmware.com"],
            conf.dns_suffixes,
            "suffixes",
        )

        nics = conf.nics
        ipv40 = nics[0].staticIpv4

        self.assertEqual(2, len(nics), "nics")
        self.assertEqual("NIC1", nics[0].name, "nic0")
        self.assertEqual("00:50:56:a6:8c:08", nics[0].mac, "mac0")
        self.assertEqual(BootProtoEnum.STATIC, nics[0].bootProto, "bootproto0")
        self.assertEqual("10.20.87.154", ipv40[0].ip, "ipv4Addr0")
        self.assertEqual("255.255.252.0", ipv40[0].netmask, "ipv4Mask0")
        self.assertEqual(2, len(ipv40[0].gateways), "ipv4Gw0")
        self.assertEqual("10.20.87.253", ipv40[0].gateways[0], "ipv4Gw0_0")
        self.assertEqual("10.20.87.105", ipv40[0].gateways[1], "ipv4Gw0_1")

        self.assertEqual(1, len(nics[0].staticIpv6), "ipv6Cnt0")
        self.assertEqual(
            "fc00:10:20:87::154", nics[0].staticIpv6[0].ip, "ipv6Addr0"
        )

        self.assertEqual("NIC2", nics[1].name, "nic1")
        self.assertTrue(not nics[1].staticIpv6, "ipv61 dhcp")

    def test_config_file_dhcp_2nics(self):
        """Tests Config class for a configuration with two DHCP NICs."""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        conf = Config(cf)
        nics = conf.nics
        self.assertEqual(2, len(nics), "nics")
        self.assertEqual("NIC1", nics[0].name, "nic0")
        self.assertEqual("00:50:56:a6:8c:08", nics[0].mac, "mac0")
        self.assertEqual(BootProtoEnum.DHCP, nics[0].bootProto, "bootproto0")

    def test_config_password(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        cf._insertKey("PASSWORD|-PASS", "test-password")
        cf._insertKey("PASSWORD|RESET", "no")

        conf = Config(cf)
        self.assertEqual("test-password", conf.admin_password, "password")
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

        network_config = get_network_data_from_vmware_cust_cfg(config, False)

        self.assertEqual(2, network_config.get("version"))

        ethernets = network_config.get("ethernets")

        for _, config in ethernets.items():
            self.assertTrue(isinstance(config, dict))
            name_servers = config.get("nameservers").get("addresses")
            dns_suffixes = config.get("nameservers").get("search")
            self.assertEqual(
                ["10.20.145.1", "10.20.145.2"], name_servers, "dns"
            )
            self.assertEqual(
                ["eng.vmware.com", "proxy.vmware.com"],
                dns_suffixes,
                "suffixes",
            )

    def test_get_config_dns_suffixes(self):
        """Tests if get_network_from_vmware_cust_cfg properly
        generates nameservers and dns settings from a
        specified configuration"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        config = Config(cf)

        network_config = get_network_data_from_vmware_cust_cfg(config, False)

        self.assertEqual(2, network_config.get("version"))

        ethernets = network_config.get("ethernets")

        for _, config in ethernets.items():
            self.assertTrue(isinstance(config, dict))
            name_servers = config.get("nameservers").get("addresses")
            dns_suffixes = config.get("nameservers").get("search")
            self.assertEqual(None, name_servers, "dns")
            self.assertEqual(["eng.vmware.com"], dns_suffixes, "suffixes")

    def test_get_nics_list_dhcp(self):
        """Tests if NicConfigurator properly calculates ethernets
        for a configuration with a list of DHCP NICs"""
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        config = Config(cf)

        nicConfigurator = NicConfigurator(
            config.nics, config.name_servers, config.dns_suffixes, False
        )
        ethernets_dict = nicConfigurator.generate()

        self.assertTrue(isinstance(ethernets_dict, dict))
        self.assertEqual(2, len(ethernets_dict), "number of ethernets")

        for name, config in ethernets_dict.items():
            if name == "NIC1":
                self.assertEqual(
                    "00:50:56:a6:8c:08",
                    config.get("match").get("macaddress"),
                    "mac address of NIC1",
                )
                self.assertEqual(
                    True, config.get("wakeonlan"), "wakeonlan of NIC1"
                )
                self.assertEqual(
                    True, config.get("dhcp4"), "DHCPv4 enablement of NIC1"
                )
                self.assertEqual(
                    False,
                    config.get("dhcp4-overrides").get("use-dns"),
                    "use-dns enablement for dhcp4-overrides of NIC1",
                )
            if name == "NIC2":
                self.assertEqual(
                    "00:50:56:a6:5a:de",
                    config.get("match").get("macaddress"),
                    "mac address of NIC2",
                )
                self.assertEqual(
                    True, config.get("wakeonlan"), "wakeonlan of NIC2"
                )
                self.assertEqual(
                    True, config.get("dhcp4"), "DHCPv4 enablement of NIC2"
                )
                self.assertEqual(
                    False,
                    config.get("dhcp4-overrides").get("use-dns"),
                    "use-dns enablement for dhcp4-overrides of NIC2",
                )

    def test_get_nics_list_static(self):
        """Tests if NicConfigurator properly calculates ethernets
        for a configuration with 2 static NICs"""
        cf = ConfigFile("tests/data/vmware/cust-static-2nic.cfg")

        config = Config(cf)

        nicConfigurator = NicConfigurator(
            config.nics, config.name_servers, config.dns_suffixes, False
        )
        ethernets_dict = nicConfigurator.generate()

        self.assertTrue(isinstance(ethernets_dict, dict))
        self.assertEqual(2, len(ethernets_dict), "number of ethernets")

        for name, config in ethernets_dict.items():
            print(config)
            if name == "NIC1":
                self.assertEqual(
                    "00:50:56:a6:8c:08",
                    config.get("match").get("macaddress"),
                    "mac address of NIC1",
                )
                self.assertEqual(
                    True, config.get("wakeonlan"), "wakeonlan of NIC1"
                )
                self.assertEqual(
                    False, config.get("dhcp4"), "DHCPv4 enablement of NIC1"
                )
                self.assertEqual(
                    False, config.get("dhcp6"), "DHCPv6 enablement of NIC1"
                )
                self.assertEqual(
                    ["10.20.87.154/22", "fc00:10:20:87::154/64"],
                    config.get("addresses"),
                    "IP addresses of NIC1",
                )
                self.assertEqual(
                    [
                        {"to": "10.20.84.0/22", "via": "10.20.87.253"},
                        {"to": "10.20.84.0/22", "via": "10.20.87.105"},
                        {
                            "to": "fc00:10:20:87::/64",
                            "via": "fc00:10:20:87::253",
                        },
                    ],
                    config.get("routes"),
                    "routes of NIC1",
                )
            if name == "NIC2":
                self.assertEqual(
                    "00:50:56:a6:ef:7d",
                    config.get("match").get("macaddress"),
                    "mac address of NIC2",
                )
                self.assertEqual(
                    True, config.get("wakeonlan"), "wakeonlan of NIC2"
                )
                self.assertEqual(
                    False, config.get("dhcp4"), "DHCPv4 enablement of NIC2"
                )
                self.assertEqual(
                    ["192.168.6.102/16"],
                    config.get("addresses"),
                    "IP addresses of NIC2",
                )
                self.assertEqual(
                    [
                        {"to": "192.168.0.0/16", "via": "192.168.0.10"},
                    ],
                    config.get("routes"),
                    "routes of NIC2",
                )

    def test_custom_script(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertIsNone(conf.custom_script_name)
        cf._insertKey("CUSTOM-SCRIPT|SCRIPT-NAME", "test-script")
        conf = Config(cf)
        self.assertEqual("test-script", conf.custom_script_name)

    def test_post_gc_status(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertFalse(conf.post_gc_status)
        cf._insertKey("MISC|POST-GC-STATUS", "YES")
        conf = Config(cf)
        self.assertTrue(conf.post_gc_status)

    def test_no_default_run_post_script(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertFalse(conf.default_run_post_script)
        cf._insertKey("MISC|DEFAULT-RUN-POST-CUST-SCRIPT", "NO")
        conf = Config(cf)
        self.assertFalse(conf.default_run_post_script)

    def test_yes_default_run_post_script(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        cf._insertKey("MISC|DEFAULT-RUN-POST-CUST-SCRIPT", "yes")
        conf = Config(cf)
        self.assertTrue(conf.default_run_post_script)


class TestVmwareNetConfig(CiTestCase):
    """Test conversion of vmware config to cloud-init config."""

    maxDiff = None

    def _get_NicConfigurator(self, text):
        fp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.tmp_dir(), delete=False
            ) as fp:
                fp.write(text)
                fp.close()
            cfg = Config(ConfigFile(fp.name))
            return NicConfigurator(
                cfg.nics,
                cfg.name_servers,
                cfg.dns_suffixes,
                use_system_devices=False,
            )
        finally:
            if fp:
                os.unlink(fp.name)

    def test_static_nic_without_ipv4_netmask(self):
        """netmask is optional for static ipv4 configuration."""
        config = textwrap.dedent(
            """\
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
            """
        )
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            {
                "NIC1": {
                    "match": {"macaddress": "00:50:56:a6:8c:08"},
                    "wakeonlan": True,
                    "dhcp4": False,
                    "addresses": ["10.20.87.154/32"],
                    "set-name": "NIC1",
                }
            },
            nc.generate(),
        )

    def test_static_nic_without_ipv6_netmask(self):
        """netmask is mandatory for static ipv6 configuration."""
        config = textwrap.dedent(
            """\
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
            IPv6ADDR|1 = fc00:10:20:87::154
            """
        )
        nc = self._get_NicConfigurator(config)
        with self.assertRaises(ValueError):
            nc.generate()

    def test_non_primary_nic_with_gateway(self):
        """A non primary nic set can have a gateway."""
        config = textwrap.dedent(
            """\
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
            """
        )
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            {
                "NIC1": {
                    "match": {"macaddress": "00:50:56:a6:8c:08"},
                    "wakeonlan": True,
                    "dhcp4": False,
                    "addresses": ["10.20.87.154/22"],
                    "routes": [{"to": "10.20.84.0/22", "via": "10.20.87.253"}],
                    "set-name": "NIC1",
                }
            },
            nc.generate(),
        )

    def test_cust_non_primary_nic_with_gateway_(self):
        """A customer non primary nic set can have a gateway."""
        config = textwrap.dedent(
            """\
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
            """
        )
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            {
                "NIC1": {
                    "match": {"macaddress": "00:50:56:ac:d1:8a"},
                    "wakeonlan": True,
                    "dhcp4": False,
                    "addresses": ["100.115.223.75/24"],
                    "routes": [
                        {"to": "100.115.223.0/24", "via": "100.115.223.254"}
                    ],
                    "set-name": "NIC1",
                    "nameservers": {"addresses": ["8.8.8.8"]},
                }
            },
            nc.generate(),
        )

    def test_a_primary_nic_with_gateway(self):
        """A primary nic set can have a gateway."""
        config = textwrap.dedent(
            """\
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
            """
        )
        nc = self._get_NicConfigurator(config)
        self.assertEqual(
            {
                "NIC1": {
                    "match": {"macaddress": "00:50:56:a6:8c:08"},
                    "wakeonlan": True,
                    "dhcp4": False,
                    "addresses": ["10.20.87.154/22"],
                    "routes": [{"to": "0.0.0.0/0", "via": "10.20.87.253"}],
                    "set-name": "NIC1",
                }
            },
            nc.generate(),
        )

    def test_meta_data(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertIsNone(conf.meta_data_name)
        cf._insertKey("CLOUDINIT|METADATA", "test-metadata")
        conf = Config(cf)
        self.assertEqual("test-metadata", conf.meta_data_name)

    def test_user_data(self):
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")
        conf = Config(cf)
        self.assertIsNone(conf.user_data_name)
        cf._insertKey("CLOUDINIT|USERDATA", "test-userdata")
        conf = Config(cf)
        self.assertEqual("test-userdata", conf.user_data_name)
