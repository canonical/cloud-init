# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit.tests.helpers import CiTestCase

from . import _get_distro


class TestopenSUSE(CiTestCase):

    def test_get_distro(self):
        distro = _get_distro("opensuse")
        self.assertEqual(distro.osfamily, 'suse')
