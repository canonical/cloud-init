# This file is part of cloud-init. See LICENSE file for license information.
import pytest

from cloudinit import atomic_helper, util
from tests.unittests.helpers import get_distro


class TestGentoo:
    def test_write_hostname(self, tmp_path):
        distro = get_distro("gentoo")
        hostname = "myhostname"
        hostfile = tmp_path / "hostfile"
        distro._write_hostname(hostname, hostfile)
        if distro.uses_systemd():
            assert "myhostname\n" == util.load_text_file(hostfile)
        else:
            assert 'hostname="myhostname"\n' == util.load_text_file(hostfile)

    def test_write_existing_hostname_with_comments(self, tmp_path):
        distro = get_distro("gentoo")
        hostname = "myhostname"
        contents = '#This is the hostname\nhostname="localhost"'
        hostfile = tmp_path / "hostfile"
        atomic_helper.write_file(hostfile, contents, omode="w")
        distro._write_hostname(hostname, hostfile)
        if distro.uses_systemd():
            assert (
                "#This is the hostname\nmyhostname\n"
                == util.load_text_file(hostfile)
            )
        else:
            assert (
                '#This is the hostname\nhostname="myhostname"\n'
                == util.load_text_file(hostfile)
            )


@pytest.fixture
def no_systemd(mocker):
    mocker.patch("cloudinit.distros.uses_systemd", return_value=False)


@pytest.mark.usefixtures("no_systemd")
class TestGentooOpenRC(TestGentoo):
    pass
