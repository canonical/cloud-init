# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.distros.parsers.ifconfig import Ifconfig
from tests.unittests.helpers import TestCase, readResource


class TestSysConfHelper(TestCase):
    def test_parse_freebsd(self):
        ifs_txt = readResource("netinfo/freebsd-ifconfig-output")
        ifs = Ifconfig().parse(ifs_txt)
