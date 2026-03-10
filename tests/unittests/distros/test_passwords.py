# This file is part of cloud-init. See LICENSE file for license information.


import pytest

from tests.unittests.helpers import get_distro, mock

USER = "foo_user"


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch(
        "cloudinit.log.security_event_log.get_host_ip", return_value=None
    )


@mock.patch("cloudinit.distros.subp.subp")
class TestChpasswd:

    @pytest.mark.parametrize(
        "plist_in,hashed,expected",
        [
            pytest.param(
                (("u1", "pw1"), ("u2", "pw2")),
                False,
                [
                    mock.call(["chpasswd"], data="u1:pw1\nu2:pw2\n"),
                ],
                id="clear_text_passwords",
            ),
            pytest.param(
                (("u1", "hash1"), ("u2", "hash2")),
                True,
                [
                    mock.call(["chpasswd", "-e"], data="u1:hash1\nu2:hash2\n"),
                ],
                id="hashed_passwords",
            ),
        ],
    )
    def test_create_options(
        self,
        m_subp,
        plist_in,
        hashed,
        expected,
        caplog,
    ):
        dist = get_distro("ubuntu")
        dist.chpasswd(plist_in=plist_in, hashed=hashed)
        assert m_subp.call_args_list == expected
        for user in ("u1", "u2"):
            assert f"authn_password_change:cloud-init,{user}" in caplog.text
