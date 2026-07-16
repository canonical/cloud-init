# This file is part of cloud-init. See LICENSE file for license information.

from tests.unittests.helpers import get_distro, mock

M_PATH = "cloudinit.distros.openbsd."


class TestOpenBSD:
    @mock.patch(M_PATH + "subp.subp")
    def test_add_user(self, m_subp):
        distro = get_distro("openbsd")
        assert True is distro.add_user("me2", uid=1234, default=False)
        assert [
            mock.call(
                ["useradd", "-m", "me2"], logstring=["useradd", "-m", "me2"]
            )
        ] == m_subp.call_args_list

    def test_unlock_passwd(self, caplog):
        distro = get_distro("openbsd")
        distro.unlock_passwd("me2")
        assert (
            "OpenBSD password lock is not reversible, "
            "ignoring unlock for user me2" in caplog.text
        )
