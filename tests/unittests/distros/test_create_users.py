# This file is part of cloud-init. See LICENSE file for license information.

from typing import List

import pytest

from cloudinit import distros, features, ssh_util
from cloudinit.util import should_log_deprecation
from tests.unittests.helpers import mock
from tests.unittests.util import abstract_to_concrete

USER = "foo_user"


@pytest.fixture(autouse=True)
def common_mocks(mocker):
    mocker.patch("cloudinit.distros.util.system_is_snappy", return_value=False)


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
    def dist(self):
        return abstract_to_concrete(distros.Distro)(
            name="test", cfg=None, paths=None
        )

    @pytest.mark.parametrize(
        "create_kwargs,expected",
        [
            pytest.param(
                {},
                [
                    _useradd2call([USER, "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="basic",
            ),
            pytest.param(
                {"no_create_home": True},
                [
                    _useradd2call([USER, "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="no_home",
            ),
            pytest.param(
                {"system": True},
                [
                    _useradd2call([USER, "--system", "-M"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="system_user",
            ),
            pytest.param(
                {"create_no_home": False},
                [
                    _useradd2call([USER, "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="explicit_no_home_false",
            ),
            pytest.param(
                {"lock_passwd": False},
                [_useradd2call([USER, "-m"])],
                id="unlocked",
            ),
            pytest.param(
                {"passwd": "passfoo"},
                [
                    _useradd2call([USER, "--password", "passfoo", "-m"]),
                    mock.call(["passwd", "-l", USER]),
                ],
                id="set_password",
            ),
        ],
    )
    def test_create_options(self, m_subp, dist, create_kwargs, expected):
        dist.create_user(name=USER, **create_kwargs)
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_group_added(self, m_is_group, m_subp, dist):
        m_is_group.return_value = False
        dist.create_user(USER, groups=["group1"])
        expected = [
            mock.call(["groupadd", "group1"]),
            _useradd2call([USER, "--groups", "group1", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group")
    def test_only_new_group_added(self, m_is_group, m_subp, dist):
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
    def test_create_groups_with_whitespace_string(
        self, m_is_group, m_subp, dist
    ):
        # groups supported as a comma delimeted string even with white space
        m_is_group.return_value = False
        dist.create_user(USER, groups="group1, group2")
        expected = [
            mock.call(["groupadd", "group1"]),
            mock.call(["groupadd", "group2"]),
            _useradd2call([USER, "--groups", "group1,group2", "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert m_subp.call_args_list == expected

    @mock.patch("cloudinit.distros.util.is_group", return_value=False)
    def test_create_groups_with_dict_deprecated(
        self, m_is_group, m_subp, dist, caplog
    ):
        """users.groups supports a dict value, but emit deprecation log."""
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
            if should_log_deprecation(
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
    def test_create_groups_with_list(self, m_is_group, m_subp, dist, caplog):
        """users.groups supports a list value."""
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

    def test_explicit_sudo_false(self, m_subp, dist, caplog):
        dist.create_user(USER, sudo=False)
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]

        expected_levels = (
            ["WARNING", "DEPRECATED"]
            if should_log_deprecation(
                "22.3", features.DEPRECATION_INFO_BOUNDARY
            )
            else ["INFO"]
        )
        assert caplog.records[1].levelname in expected_levels
        assert (
            "The value of 'false' in user foo_user's 'sudo' "
            "config is deprecated in 22.3 and scheduled to be removed"
            " in 27.3. Use 'null' instead."
        ) in caplog.text

    def test_explicit_sudo_none(self, m_subp, dist, caplog):
        dist.create_user(USER, sudo=None)
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        assert "WARNING" not in caplog.text
        assert "DEPRECATED" not in caplog.text

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_setup_ssh_authorized_keys_with_string(
        self, m_setup_user_keys, m_subp, dist
    ):
        """ssh_authorized_keys allows string and calls setup_user_keys."""
        dist.create_user(USER, ssh_authorized_keys="mykey")
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
            mock.call(["passwd", "-l", USER]),
        ]
        m_setup_user_keys.assert_called_once_with({"mykey"}, USER)

    @mock.patch("cloudinit.ssh_util.setup_user_keys")
    def test_setup_ssh_authorized_keys_with_list(
        self, m_setup_user_keys, m_subp, dist
    ):
        """ssh_authorized_keys allows lists and calls setup_user_keys."""
        dist.create_user(USER, ssh_authorized_keys=["key1", "key2"])
        assert m_subp.call_args_list == [
            _useradd2call([USER, "-m"]),
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
