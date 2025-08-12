# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from tests.unittests.helpers import get_distro


class TestArch:
    def test_get_distro(self, tmp_path):
        distro = get_distro("arch")
        hostname = "myhostname"
        hostfile = tmp_path / "hostfile"
        distro._write_hostname(hostname, hostfile)
        assert hostname + "\n" == util.load_text_file(hostfile)
