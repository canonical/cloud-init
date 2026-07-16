# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import get_distro


class TestAOSC:
    def test_get_distro(self):
        distro = get_distro("aosc")
        assert distro.osfamily == "aosc"
