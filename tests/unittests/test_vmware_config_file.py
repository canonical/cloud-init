# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2016 VMware INC.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import sys
import unittest

from cloudinit.sources.helpers.vmware.imc.boot_proto import BootProtoEnum
from cloudinit.sources.helpers.vmware.imc.config import Config
from cloudinit.sources.helpers.vmware.imc.config_file import ConfigFile

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger(__name__)


class TestVmwareConfigFile(unittest.TestCase):

    def test_utility_methods(self):
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

    def test_configfile_static_2nics(self):
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
        cf = ConfigFile("tests/data/vmware/cust-dhcp-2nic.cfg")

        conf = Config(cf)
        nics = conf.nics
        self.assertEqual(2, len(nics), "nics")
        self.assertEqual('NIC1', nics[0].name, "nic0")
        self.assertEqual('00:50:56:a6:8c:08', nics[0].mac, "mac0")
        self.assertEqual(BootProtoEnum.DHCP, nics[0].bootProto, "bootproto0")

# vi: ts=4 expandtab
