# This file is part of cloud-init. See LICENSE file for license information.

import cloudinit.util
from tests.unittests.helpers import get_distro, mock

M_PATH = "cloudinit.distros."


class TestDragonFlyBSD:
    @mock.patch(M_PATH + "subp.subp")
    def test_add_user(self, m_subp):
        distro = get_distro("dragonflybsd")
        assert True is distro.add_user("me2", uid=1234, default=False)
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

    def test_unlock_passwd(self, caplog):
        distro = get_distro("dragonflybsd")
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
