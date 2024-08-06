# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.distros import _get_distro
from tests.unittests.helpers import CiTestCase


class TestAOSC(CiTestCase):
    def test_get_distro(self):
        distro = _get_distro("aosc")
        self.assertEqual(distro.osfamily, "aosc")
