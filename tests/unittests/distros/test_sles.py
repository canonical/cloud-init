# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import get_distro


class TestSLES:
    def test_get_distro(self):
        distro = get_distro("sles")
        assert distro.osfamily == "suse"
