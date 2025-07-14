# This file is part of cloud-init. See LICENSE file for license information.

from pathlib import Path
from typing import List

import pytest

from cloudinit import distros, features, lifecycle, ssh_util
from tests.unittests.helpers import get_distro, mock
from tests.unittests.util import abstract_to_concrete

USER = "foo_user"


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch("cloudinit.distros.util.system_is_snappy", return_value=False)


def _chpasswdmock(name: str, password: str, hashed: bool = False):
    """Return a mock of chpasswd call based on args"""
    cmd = ["chpasswd", "-e"] if hashed else ["chpasswd"]
    return mock.call(
        cmd, data=f"{name}:{password}", logstring=f"chpasswd for {name}"
    )


def _useradd2call(args: List[str]):
    # return a mock call for the useradd command in args
    # with expected 'logstring'.
    args = ["useradd"] + args
    logcmd = list(args)
    for i in range(len(args)):
        if args[i] in ("--password",):
            logcmd[i + 1] = "REDACTED"
    return mock.call(args, logstring=logcmd)


@mock.patch("cloudinit.distros.subp.subp")
class TestCreateUser:
    @pytest.fixture()
    def dist(self, tmpdir):
        d = abstract_to_concrete(distros.Distro)(
            name="test", cfg=None, paths=None
        )
        # Monkey patch /etc/shadow files to tmpdir
        d.shadow_fn = tmpdir.join(d.shadow_fn).strpath
        d.shadow_extrausers_fn = tmpdir.join(d.shadow_extrausers_fn).strpath
        return d

    @pytest.mark.parametrize(
        "create_kwargs,is_snappy,expected",
        [
            pytest.param(
                {},
                False,
                [
                    _useradd2call([USER, "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="basic",
            ),
            pytest.param(
                {},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="basic_snappy",
            ),
            pytest.param(
                {"no_create_home": True},
                False,
                [
                    _useradd2call([USER, "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="no_home",
            ),
            pytest.param(
                {"no_create_home": True},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="no_home_snappy",
            ),
            pytest.param(
                {"system": True},
                False,
                [
                    _useradd2call([USER, "--system", "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="system_user",
            ),
            pytest.param(
                {"system": True},
                True,
                [
                    _useradd2call([USER, "--extrausers", "--system", "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="system_user_snappy",
            ),
            pytest.param(
                {"create_no_home": False},
                False,
                [
                    _useradd2call([USER, "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="explicit_no_home_false",
            ),
            pytest.param(
                {"create_no_home": False},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="explicit_no_home_false_snappy",
            ),
            pytest.param(
                {"lock_passwd": False},
                False,
                [_useradd2call([USER, "-m"])],
                id="unlocked",
            ),
            pytest.param(
                {"lock_passwd": False},
                True,
                [_useradd2call([USER, "--extrausers", "-m"])],
                id="unlocked_snappy",
            ),
            pytest.param(
                {"passwd": "$6$rounds=..."},
                False,
                [
                    _useradd2call([USER, "--password", "$6$rounds=...", "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_implicit_encrypted_password",
            ),
            pytest.param(
                {"passwd": "$6$rounds=..."},
                True,
                [
                    _useradd2call(
                        [
                            USER,
                            "--extrausers",
                            "--password",
                            "$6$rounds=...",
                            "-m",
                        ]
                    ),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_implicit_encrypted_password_snappy",
            ),
            pytest.param(
                {"passwd": ""},
                False,
                [
                    _useradd2call([USER, "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_empty_passwd_new_user",
            ),
            pytest.param(
                {"passwd": ""},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_empty_passwd_new_user_snappy",
            ),
            pytest.param(
                {"plain_text_passwd": "clearfoo"},
                False,
                [
                    _useradd2call([USER, "-m"]),
                    _chpasswdmock(USER, "clearfoo"),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_plain_text_password",
            ),
            pytest.param(
                {"plain_text_passwd": "clearfoo"},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-m"]),
                    _chpasswdmock(USER, "clearfoo"),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_plain_text_password_snappy",
            ),
            pytest.param(
                {"hashed_passwd": "$6$rounds=..."},
                False,
                [
                    _useradd2call([USER, "-m"]),
                    _chpasswdmock(USER, "$6$rounds=...", hashed=True),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_explicitly_hashed_password",
            ),
            pytest.param(
                {"hashed_passwd": "$6$rounds=..."},
                True,
                [
                    _useradd2call([USER, "--extrausers", "-m"]),
                    _chpasswdmock(USER, "$6$rounds=...", hashed=True),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_explicitly_hashed_password_snappy",
            ),
        ],
    )
    @mock.patch("cloudinit.distros.util.is_user", return_value=False)
    def test_create_options(
        self,
        m_is_user,
        m_subp,
        dist,
        create_kwargs,
        is_snappy,
        expected,
        mocker,
    ):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=is_snappy
        )
        dist.create_user(name=USER, **create_kwargs)
        assert m_subp.call_args_list == expected

    @pytest.mark.parametrize(
        "shadow_content,distro_name,is_snappy,expected_logs",
        (
            pytest.param(
                {"/etc/shadow": f"dnsmasq:!:\n{USER}:!:"},
                "ubuntu",
                False,
                [
                    "Not unlocking blank password for existing user "
                    "foo_user. 'lock_passwd: false' present in user-data "
                    "but no existing password set and no "
                    "'plain_text_passwd'/'hashed_passwd' provided in "
                    "user-data"
                ],
                id="no_unlock_on_locked_empty_user_passwd",
            ),
            pytest.param(
                {"/var/lib/extrausers/shadow": f"dnsmasq::\n{USER}:!:"},
                "ubuntu",
                True,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_in_snappy_on_locked_empty_user_passwd_in_extrausers",
            ),
            pytest.param(
                {"/etc/shadow": f"dnsmasq::\n{USER}::"},
                "alpine",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_user_passwd_alpine",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}::"},
                "dragonflybsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_user_passwd_dragonflybsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*:"},
                "dragonflybsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format1_empty_user_passwd_dragonflybsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*LOCKED*:"},
                "dragonflybsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format2_empty_user_passwd_dragonflybsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}::"},
                "freebsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_user_passwd_freebsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*:"},
                "freebsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format1_empty_user_passwd_freebsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*LOCKED*:"},
                "freebsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format2_empty_user_passwd_freebsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}::"},
                "netbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_format1_user_passwd_netbsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*************:"},
                "netbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_format2_user_passwd_netbsd",
            ),
            pytest.param(
                {
                    "/etc/master.passwd": f"dnsmasq::\n{USER}:*LOCKED**************:"  # noqa: E501
                },
                "netbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_empty_user_passwd_netbsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}::"},
                "openbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_empty_user_passwd_openbsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*:"},
                "openbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format1_empty_user_passwd_openbsd",
            ),
            pytest.param(
                {"/etc/master.passwd": f"dnsmasq::\n{USER}:*************:"},
                "openbsd",
                False,
                ["Not unlocking blank password for existing user foo_user."],
                id="no_unlock_on_locked_format2_empty_user_passwd_openbsd",
            ),
        ),
    )
    def test_avoid_unlock_preexisting_user_empty_password(
        self,
        m_subp,
        shadow_content,
        distro_name,
        is_snappy,
        expected_logs,
        caplog,
        mocker,
        tmpdir,
    ):
        dist = get_distro(distro_name)
        dist.shadow_fn = tmpdir.join(dist.shadow_fn).strpath
        dist.shadow_extrausers_fn = tmpdir.join(
            dist.shadow_extrausers_fn
        ).strpath

        mocker.patch("cloudinit.distros.util.is_user", return_value=True)
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=is_snappy
        )
        for filename, content in shadow_content.items():
            if dist.shadow_fn == tmpdir.join(filename).strpath:
                shadow_file = Path(dist.shadow_fn)
                shadow_file.parent.mkdir(parents=True, exist_ok=True)
            elif dist.shadow_extrausers_fn == tmpdir.join(filename).strpath:
                shadow_file = Path(dist.shadow_extrausers_fn)
                shadow_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                raise AssertionError(
                    f"Shadow file path {filename} not defined for distro"
                    f" {dist.name}"
                )
            shadow_file.write_text(content)
        unlock_passwd = mocker.patch.object(dist, "unlock_passwd")
        dist.create_user(name=USER, lock_passwd=False)
        for log in expected_logs:
            assert log in caplog.text
        unlock_passwd.assert_not_called()
        assert m_subp.call_args_list == []

    @pytest.mark.parametrize(
        "create_kwargs,expected,expected_logs",
        [
            pytest.param(
                {"passwd": "$6$rounds=..."},
                [mock.call(["passwd", "-l", USER])],
                [
                    "'passwd' in user-data is ignored for existing user "
                    "foo_user"
                ],
                id="skip_passwd_set_on_existing_user",
            ),
            pytest.param(
                {"plain_text_passwd": "clearfoo"},
                [
                    _chpasswdmock(USER, "clearfoo"),
                    mock.call(["passwd", "-l", USER]),
                ],
                [],
                id="set_plain_text_password_on_existing_user",
            ),
            pytest.param(
                {"hashed_passwd": "$6$rounds=..."},
                [
                    _chpasswdmock(USER, "$6$rounds=...", hashed=True),
                    mock.call(["passwd", "-l", USER]),
                ],
                [],
                id="set_explicitly_hashed_password",
            ),
        ],
    )
    @mock.patch("cloudinit.distros.util.is_user", return_value=True)
    def test_create_passwd_existing_user(
        self,
        m_is_user,
        m_subp,
        create_kwargs,
        expected,
        expected_logs,
        dist,
        caplog,
        tmpdir,
        mocker,
    ):
        """When user exists, don't unlock on empty or locked passwords."""
        dist.create_user(name=USER, **create_kwargs)
        for log in expected_logs:
            assert log in caplog.text
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_group_added(self, m_is_group, m_subp, dist, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        m_is_group.return_value = False
        dist.create_user(USER, groups=["group1"])
        expected = [
            mock.call(["groupadd", "group1"]),
            _useradd2call([USER, "--groups", "group1", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_snappy_group_added(self, m_is_group, m_subp, dist, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        m_is_group.return_value = False
        dist.create_user(USER, groups=["group1"])
        expected = [
            mock.call(["groupadd", "group1", "--extrausers"]),
            _useradd2call([USER, "--extrausers", "--groups", "group1", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_only_new_group_added(self, m_is_group, m_subp, dist, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        ex_groups = ["existing_group"]
        groups = ["group1", ex_groups[0]]
        m_is_group.side_effect = lambda m: m in ex_groups
        dist.create_user(USER, groups=groups)
        expected = [
            mock.call(["groupadd", "group1"]),
            _useradd2call([USER, "--groups", ",".join(groups), "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_snappy_only_new_group_added(
        self, m_is_group, m_subp, dist, mocker
    ):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        ex_groups = ["existing_group"]
        groups = ["group1", ex_groups[0]]
        m_is_group.side_effect = lambda m: m in ex_groups
        dist.create_user(USER, groups=groups)
        expected = [
            mock.call(["groupadd", "group1", "--extrausers"]),
            _useradd2call(
                [USER, "--extrausers", "--groups", ",".join(groups), "-m"]
            ),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_create_groups_with_whitespace_string(
        self, m_is_group, m_subp, dist, mocker
    ):
        # groups supported as a comma delimeted string even with white space
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        m_is_group.return_value = False
        dist.create_user(USER, groups="group1, group2")
        expected = [
            mock.call(["groupadd", "group1"]),
            mock.call(["groupadd", "group2"]),
            _useradd2call([USER, "--groups", "group1,group2", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_snappy_create_groups_with_whitespace_string(
        self, m_is_group, m_subp, dist, mocker
    ):
        # groups supported as a comma delimeted string even with white space
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        m_is_group.return_value = False
        dist.create_user(USER, groups="group1, group2")
        expected = [
            mock.call(["groupadd", "group1", "--extrausers"]),
            mock.call(["groupadd", "group2", "--extrausers"]),
            _useradd2call(
                [USER, "--extrausers", "--groups", "group1,group2", "-m"]
            ),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group", return_value=False)
    def test_create_groups_with_dict_deprecated(
        self, m_is_group, m_subp, dist, caplog, mocker
    ):
        """users.groups supports a dict value, but emit deprecation log."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, groups={"group1": None, "group2": None})
        expected = [
            mock.call(["groupadd", "group1"]),
            mock.call(["groupadd", "group2"]),
            _useradd2call([USER, "--groups", "group1,group2", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

        expected_levels = (
            ["WARNING", "DEPRECATED"]
            if lifecycle.should_log_deprecation(
                "23.1", features.DEPRECATION_INFO_BOUNDARY
            )
            else ["INFO"]
        )
        assert caplog.records[0].levelname in expected_levels
        assert (
            "The user foo_user has a 'groups' config value of type dict"
            in caplog.records[0].message
        )
        assert "Use a comma-delimited" in caplog.records[0].message

    @mock.patch("cloudinit.distros.util.is_group", return_value=False)
    def test_create_groups_with_list(
        self, m_is_group, m_subp, dist, caplog, mocker
    ):
        """users.groups supports a list value."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, groups=["group1", "group2"])
        expected = [
            mock.call(["groupadd", "group1"]),
            mock.call(["groupadd", "group2"]),
            _useradd2call([USER, "--groups", "group1,group2", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected
        assert "WARNING" not in caplog.text
        assert "DEPRECATED" not in caplog.text

    @mock.patch("cloudinit.distros.util.is_group", return_value=False)
    def test_snappy_create_groups_with_list(
        self, m_is_group, m_subp, dist, caplog, mocker
    ):
        """users.groups supports a list value."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        dist.create_user(USER, groups=["group1", "group2"])
        expected = [
            mock.call(["groupadd", "group1", "--extrausers"]),
            mock.call(["groupadd", "group2", "--extrausers"]),
            _useradd2call(
                [USER, "--extrausers", "--groups", "group1,group2", "-m"]
            ),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected
        assert "WARNING" not in caplog.text
        assert "DEPRECATED" not in caplog.text

    def test_explicit_sudo_false(self, m_subp, dist, caplog, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, sudo=False)
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]

        expected_levels = (
            ["WARNING", "DEPRECATED"]
            if lifecycle.should_log_deprecation(
                "22.2", features.DEPRECATION_INFO_BOUNDARY
            )
            else ["INFO"]
        )
        assert caplog.records[1].levelname in expected_levels
        assert (
            "The value of 'false' in user foo_user's 'sudo' "
            "config is deprecated in 22.2 and scheduled to be removed"
            " in 27.2. Use 'null' instead."
        ) in caplog.text

    def test_explicit_sudo_none(self, m_subp, dist, caplog, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, sudo=None)
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert "WARNING" not in caplog.text
        assert "DEPRECATED" not in caplog.text

    def test_snappy_explicit_sudo_none(self, m_subp, dist, caplog, mocker):
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        dist.create_user(USER, sudo=None)
        assert m_subp.call_args_list == [
            _useradd2call([USER, "--extrausers", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert "WARNING" not in caplog.text
        assert "DEPRECATED" not in caplog.text

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_setup_ssh_authorized_keys_with_string(
        self, m_setup_user_keys, m_subp, dist, mocker
    ):
        """ssh_authorized_keys allows string and calls setup_user_keys."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, ssh_authorized_keys="mykey")
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        m_setup_user_keys.assert_called_once_with({"mykey"}, USER)

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_snappy_setup_ssh_authorized_keys_with_string(
        self, m_setup_user_keys, m_subp, dist, mocker
    ):
        """ssh_authorized_keys allows string and calls setup_user_keys."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        dist.create_user(USER, ssh_authorized_keys="mykey")
        assert m_subp.call_args_list == [
            _useradd2call([USER, "--extrausers", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        m_setup_user_keys.assert_called_once_with({"mykey"}, USER)

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_setup_ssh_authorized_keys_with_list(
        self, m_setup_user_keys, m_subp, dist, mocker
    ):
        """ssh_authorized_keys allows lists and calls setup_user_keys."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=False
        )
        dist.create_user(USER, ssh_authorized_keys=["key1", "key2"])
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        m_setup_user_keys.assert_called_once_with({"key1", "key2"}, USER)

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_snappy_setup_ssh_authorized_keys_with_list(
        self, m_setup_user_keys, m_subp, dist, mocker
    ):
        """ssh_authorized_keys allows lists and calls setup_user_keys."""
        mocker.patch(
            "cloudinit.distros.util.system_is_snappy", return_value=True
        )
        dist.create_user(USER, ssh_authorized_keys=["key1", "key2"])
        assert m_subp.call_args_list == [
            _useradd2call([USER, "--extrausers", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        m_setup_user_keys.assert_called_once_with({"key1", "key2"}, USER)

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_setup_ssh_authorized_keys_with_integer(
        self, m_setup_user_keys, m_subp, dist, caplog
    ):
        """ssh_authorized_keys warns on non-iterable/string type."""
        dist.create_user(USER, ssh_authorized_keys=-1)
        m_setup_user_keys.assert_called_once_with(set([]), USER)
        assert caplog.records[1].levelname in ["WARNING", "DEPRECATED"]
        assert (
            "Invalid type '<class 'int'>' detected for 'ssh_authorized_keys'"
            in caplog.text
        )

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_create_user_with_ssh_redirect_user_no_cloud_keys(
        self, m_setup_user_keys, m_subp, dist, caplog
    ):
        """Log a warning when trying to redirect a user no cloud ssh keys."""
        dist.create_user(USER, ssh_redirect_user="someuser")
        assert caplog.records[1].levelname in ["WARNING", "DEPRECATED"]
        assert (
            "Unable to disable SSH logins for foo_user given "
            "ssh_redirect_user: someuser. No cloud public-keys present.\n"
        ) in caplog.text
        m_setup_user_keys.assert_not_called()

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_create_user_with_ssh_redirect_user_with_cloud_keys(
        self, m_setup_user_keys, m_subp, dist
    ):
        """Disable ssh when ssh_redirect_user and cloud ssh keys are set."""
        dist.create_user(
            USER, ssh_redirect_user="someuser", cloud_public_ssh_keys=["key1"]
        )
        disable_prefix = ssh_util.DISABLE_USER_OPTS
        disable_prefix = disable_prefix.replace("$USER", "someuser")
        disable_prefix = disable_prefix.replace("$DISABLE_USER", USER)
        m_setup_user_keys.assert_called_once_with(
            {"key1"}, USER, options=disable_prefix
        )

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_create_user_with_ssh_redirect_user_does_not_disable_auth_keys(
        self, m_setup_user_keys, m_subp, dist
    ):
        """Do not disable ssh_authorized_keys when ssh_redirect_user is set."""
        dist.create_user(
            USER,
            ssh_authorized_keys="auth1",
            ssh_redirect_user="someuser",
            cloud_public_ssh_keys=["key1"],
        )
        disable_prefix = ssh_util.DISABLE_USER_OPTS
        disable_prefix = disable_prefix.replace("$USER", "someuser")
        disable_prefix = disable_prefix.replace("$DISABLE_USER", USER)
        assert m_setup_user_keys.call_args_list == [
            mock.call({"auth1"}, USER),
            mock.call({"key1"}, USER, options=disable_prefix),
        ]

    @mock.patch("cloudinit.distros.subp.which")
    def test_lock_with_usermod_if_no_passwd(self, m_which, m_subp, dist):
        """Lock uses usermod --lock if no 'passwd' cmd available."""
        m_which.side_effect = lambda m: m in ("usermod",)
        dist.lock_passwd("bob")
        assert [
            mock.call(["usermod", "--lock", "bob"])
        ] == m_subp.call_args_list

    @mock.patch("cloudinit.distros.subp.which")
    def test_lock_with_passwd_if_available(self, m_which, m_subp, dist):
        """Lock with only passwd will use passwd."""
        m_which.side_effect = lambda m: m in ("passwd",)
        dist.lock_passwd("bob")
        assert [mock.call(["passwd", "-l", "bob"])] == m_subp.call_args_list

    @mock.patch("cloudinit.distros.subp.which")
    def test_lock_raises_runtime_if_no_commands(self, m_which, m_subp, dist):
        """Lock with no commands available raises RuntimeError."""
        m_which.return_value = None
        with pytest.raises(RuntimeError):
            dist.lock_passwd("bob")
