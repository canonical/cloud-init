import unittest.mock as mock

import pytest

from cloudinit.distros.bsd import BSDNetworking
from cloudinit.distros.netbsd import Distro
from tests.unittests.distros import _get_distro
from tests.unittests.helpers import mock

try:
    # Blowfish not available in < 3.7, so this has never worked. Ignore failure
    # to import with AttributeError. We need this module imported prior to
    # patching the object, so we can't gate the version with pytest skipif.
    import cloudinit.distros.netbsd
except AttributeError:
    pass

M_PATH = "cloudinit.distros.netbsd."


class TestNetBSD:
    @mock.patch(M_PATH + "subp.subp")
    def test_add_user(self, m_subp, mocker):
        mocker.patch.object(Distro, "networking_cls", spec=BSDNetworking)
        distro = _get_distro("netbsd")
        user_created = distro.add_user("me2", uid=1234, default=False)
        assert [
            mock.call(
                ["useradd", "-m", "me2"], logstring=["useradd", "-m", "me2"]
            )
        ] == m_subp.call_args_list
        assert user_created == True

    @mock.patch(M_PATH + "subp.subp")
    def test_unlock_passwd(self, m_subp, mocker, caplog):
        mocker.patch.object(Distro, "networking_cls", spec=BSDNetworking)
        distro = _get_distro("netbsd")
        distro.unlock_passwd("me2")
        assert [
            mock.call(["usermod", "-C", "no", "me2"])
        ] == m_subp.call_args_list


@pytest.mark.parametrize("with_pkgin", (True, False))
@mock.patch("cloudinit.distros.netbsd.os")
def test_init(m_os, with_pkgin):
    print(with_pkgin)
    m_os.path.exists.return_value = with_pkgin
    cfg = {}

    # patch ifconfig -a
    with mock.patch(
        "cloudinit.distros.networking.subp.subp", return_value=("", None)
    ):
        distro = cloudinit.distros.netbsd.NetBSD("netbsd", cfg, None)
    expectation = ["pkgin", "-y", "full-upgrade"] if with_pkgin else None
    assert distro.pkg_cmd_upgrade_prefix == expectation
    assert [mock.call("/usr/pkg/bin/pkgin")] == m_os.path.exists.call_args_list
