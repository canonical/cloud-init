# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import atomic_helper, util
from tests.unittests.distros import _get_distro
from tests.unittests.helpers import CiTestCase


class TestGentoo(CiTestCase):
    def test_write_hostname(self):
        distro = _get_distro("gentoo")
        hostname = "myhostname"
        hostfile = self.tmp_path("hostfile")
        distro._write_hostname(hostname, hostfile)
        self.assertEqual(
            'hostname="myhostname"\n', util.load_text_file(hostfile)
        )

    def test_write_existing_hostname_with_comments(self):
        distro = _get_distro("gentoo")
        hostname = "myhostname"
        contents = '#This is the hostname\nhostname="localhost"'
        hostfile = self.tmp_path("hostfile")
        atomic_helper.write_file(hostfile, contents, omode="w")
        distro._write_hostname(hostname, hostfile)
        self.assertEqual(
            '#This is the hostname\nhostname="myhostname"\n',
            util.load_text_file(hostfile),
        )
