# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros.parsers.ifconfig import Ifconfig
from tests.unittests.helpers import TestCase, readResource


class TestSysConfHelper(TestCase):
    def test_parse_freebsd(self):
        """assert parsing works without any exceptions"""
        ifs_txt = readResource("netinfo/freebsd-ifconfig-output")
        Ifconfig().parse(ifs_txt)

    def test_parse_is_bridge(self):
        """assert bridge0 is_bridge"""
        ifs_txt = readResource("netinfo/freebsd-ifconfig-output")
        ifs = Ifconfig().parse(ifs_txt)
        assert ifs[2].is_bridge

    def test_parse_is_vlan(self):
        """assert re0.33 is_vlan"""
        ifs_txt = readResource("netinfo/freebsd-ifconfig-output")
        ifs = Ifconfig().parse(ifs_txt)
        assert ifs[1].is_vlan
