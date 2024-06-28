# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros.parsers.ifconfig import Ifconfig
from tests.unittests.helpers import TestCase, readResource


class TestIfconfigParserFreeBSD(TestCase):
    def setUp(self):
        super(TestIfconfigParserFreeBSD, self).setUp()
        self.ifs_txt = readResource("netinfo/freebsd-ifconfig-output")

    def test_parse_freebsd(self):
        """assert parsing works without any exceptions"""
        Ifconfig().parse(self.ifs_txt)

    def test_is_bridge(self):
        """assert bridge0 is_bridge"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["bridge0"].is_bridge

    def test_index(self):
        """assert vtnet0 index is 1"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["vtnet0"].index == 1

    def test_is_vlan(self):
        """assert re0.33 is_vlan"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["re0.33"].is_vlan

    def test_netmask(self):
        ifs = Ifconfig().parse(self.ifs_txt)
        # netmasks are Normalized from non-contiguous hex bitmasks to
        # contiguous decimal bitmasks
        assert ifs["bridge0"].inet["192.168.1.1"]["netmask"] == "255.255.255.0"
        assert ifs["lo0"].inet["127.0.0.1"]["netmask"] == "255.0.0.0"

    def test_description(self):
        """assert vnet0:11 is associated with jail: webirc"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["vnet0:11"].description == "'associated with jail: webirc'"

    def test_vtnet_options(self):
        """assert vtnet has TXCSUM"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert "txcsum" in ifs["vtnet0"].options

    def test_duplicate_mac(self):
        """
        assert that we can have duplicate macs, and that it's not an accident
        """
        self.ifs_txt = readResource(
            "netinfo/freebsd-duplicate-macs-ifconfig-output"
        )
        ifc = Ifconfig()
        ifc.parse(self.ifs_txt)
        ifs_by_mac = ifc.ifs_by_mac()
        assert len(ifs_by_mac["00:0d:3a:54:ad:1e"]) == 2
        assert (
            ifs_by_mac["00:0d:3a:54:ad:1e"][0].name
            != ifs_by_mac["00:0d:3a:54:ad:1e"][1].name
        )


class TestIfconfigParserFreeBSDCIDR(TestCase):
    def setUp(self):
        super(TestIfconfigParserFreeBSDCIDR, self).setUp()
        self.ifs_txt = readResource("netinfo/freebsd-ifconfig-cidr-output")

    def test_parse_freebsd(self):
        """assert parsing works without any exceptions"""
        Ifconfig().parse(self.ifs_txt)

    def test_netmask(self):
        ifs = Ifconfig().parse(self.ifs_txt)
        # netmasks are Normalized from CIDR to contiguous decimal bitmasks
        assert (
            ifs["vtnet0"].inet["198.51.100.13"]["netmask"] == "255.255.255.255"
        )
        assert ifs["lo0"].inet["127.0.0.1"]["netmask"] == "255.0.0.0"


class TestIfconfigParserOpenBSD(TestCase):
    def setUp(self):
        super(TestIfconfigParserOpenBSD, self).setUp()
        self.ifs_txt = readResource("netinfo/openbsd-ifconfig-output")

    def test_parse_openbsd(self):
        """assert parsing works without any exceptions"""
        Ifconfig().parse(self.ifs_txt)

    def test_is_not_physical(self):
        """assert enc0 is not physical"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert not ifs["enc0"].is_physical

    def test_is_physical(self):
        """assert enc0 is not physical"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["vio0"].is_physical

    def test_index(self):
        """assert vio0 index is 1"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["vio0"].index == 1

    def test_gif_ipv6(self):
        """assert that we can parse a gif inet6 address, despite the -->"""
        ifs = Ifconfig().parse(self.ifs_txt)
        assert ifs["gif0"].inet6["fe80::be30:5bff:fed0:471"] == {
            "prefixlen": "64",
            "scope": "link-local",
        }
