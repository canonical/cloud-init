# This file is part of cloud-init. See LICENSE file for license information.

import cloudinit.util
from cloudinit.distros.dragonflybsd import Distro
from cloudinit.distros.freebsd import FreeBSDNetworking
from tests.unittests.distros import _get_distro
from tests.unittests.helpers import mock

M_PATH = "cloudinit.distros."


class TestDragonFlyBSD:
    @mock.patch(M_PATH + "subp.subp")
    def test_add_user(self, m_subp, mocker):
        mocker.patch.object(Distro, "networking_cls", spec=FreeBSDNetworking)
        distro = _get_distro("dragonflybsd")
        distro.add_user("me2", uid=1234, default=False)
        assert [
            mock.call(
                [
                    "pw",
                    "useradd",
                    "-n",
                    "me2",
                    "-u",
                    "1234",
                    "-d/home/me2",
                    "-m",
                ],
                logstring=["pw", "useradd", "-n", "me2", "-d/home/me2", "-m"],
            )
        ] == m_subp.call_args_list

    @mock.patch(M_PATH + "subp.subp")
    def test_check_existing_password_for_user(self, m_subp, mocker):
        mocker.patch.object(Distro, "networking_cls", spec=FreeBSDNetworking)
        distro = _get_distro("dragonflybsd")
        distro._check_if_existing_password("me2")
        assert [
            mock.call(
                [
                    "grep",
                    "-q",
                    "-e",
                    "^me2::",
                    "-e",
                    "^me2:*:",
                    "-e",
                    "^me2:*LOCKED*:",
                    "/etc/master.passwd",
                ]
            )
        ] == m_subp.call_args_list

    def test_unlock_passwd(self, mocker, caplog):
        mocker.patch.object(Distro, "networking_cls", spec=FreeBSDNetworking)
        distro = _get_distro("dragonflybsd")
        distro.unlock_passwd("me2")
        assert (
            "Dragonfly BSD/FreeBSD password lock is not reversible, "
            "ignoring unlock for user me2" in caplog.text
        )


def test_find_dragonflybsd_part():
    assert cloudinit.util.find_freebsd_part("/dev/vbd0s3") == "vbd0s3"


@mock.patch("cloudinit.util.is_DragonFlyBSD")
@mock.patch("cloudinit.subp.subp")
def test_parse_mount(mock_subp, m_is_DragonFlyBSD):
    mount_out = """
vbd0s3 on / (hammer2, local)
devfs on /dev (devfs, nosymfollow, local)
/dev/vbd0s0a on /boot (ufs, local)
procfs on /proc (procfs, local)
tmpfs on /var/run/shm (tmpfs, local)
"""

    mock_subp.return_value = (mount_out, "")
    m_is_DragonFlyBSD.return_value = True
    assert cloudinit.util.parse_mount("/") == ("vbd0s3", "hammer2", "/")
