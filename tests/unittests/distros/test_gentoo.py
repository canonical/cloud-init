# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import atomic_helper, util
from tests.unittests.helpers import CiTestCase, get_distro, mock


class TestGentoo(CiTestCase):
    def test_write_hostname(self, whatever=False):
        distro = get_distro("gentoo")
        hostname = "myhostname"
        hostfile = self.tmp_path("hostfile")
        distro._write_hostname(hostname, hostfile)
        if distro.uses_systemd():
            self.assertEqual("myhostname\n", util.load_text_file(hostfile))
        else:
            self.assertEqual(
                'hostname="myhostname"\n', util.load_text_file(hostfile)
            )

    def test_write_existing_hostname_with_comments(self, whatever=False):
        distro = get_distro("gentoo")
        hostname = "myhostname"
        contents = '#This is the hostname\nhostname="localhost"'
        hostfile = self.tmp_path("hostfile")
        atomic_helper.write_file(hostfile, contents, omode="w")
        distro._write_hostname(hostname, hostfile)
        if distro.uses_systemd():
            self.assertEqual(
                "#This is the hostname\nmyhostname\n",
                util.load_text_file(hostfile),
            )
        else:
            self.assertEqual(
                '#This is the hostname\nhostname="myhostname"\n',
                util.load_text_file(hostfile),
            )


@mock.patch("cloudinit.distros.uses_systemd", return_value=False)
class TestGentooOpenRC(TestGentoo):
    pass
