# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import CiTestCase, get_distro


class TestAOSC(CiTestCase):
    def test_get_distro(self):
        distro = get_distro("aosc")
        self.assertEqual(distro.osfamily, "aosc")
