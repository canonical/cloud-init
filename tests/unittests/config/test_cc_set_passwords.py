# This file is part of cloud-init. See LICENSE file for license information.

import logging
from unittest import mock

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_set_passwords as setpass
from cloudinit.config.schema import (
    SchemaValidationError,
    get_schema,
    validate_cloudconfig_schema,
)
from tests.unittests.helpers import CiTestCase, skipUnlessJsonSchema
from tests.unittests.util import get_cloud

MODPATH = "cloudinit.config.cc_set_passwords."


@pytest.fixture()
def mock_uses_systemd(mocker):
    mocker.patch("cloudinit.distros.uses_systemd", return_value=True)


class TestHandleSSHPwauth:
    @pytest.mark.parametrize(
        "uses_systemd,cmd",
        (
            (True, ["systemctl", "status", "ssh"]),
            (False, ["service", "ssh", "status"]),
        ),
    )
    @mock.patch("cloudinit.distros.subp.subp")
    def test_unknown_value_logs_warning(
        self, m_subp, uses_systemd, cmd, caplog
    ):
        cloud = get_cloud("ubuntu")
        with mock.patch.object(
            cloud.distro, "uses_systemd", return_value=uses_systemd
        ):
            setpass.handle_ssh_pwauth("floo", cloud.distro)
        assert "Unrecognized value: ssh_pwauth=floo" in caplog.text
        assert [mock.call(cmd, capture=True)] == m_subp.call_args_list

    @pytest.mark.parametrize(
        "uses_systemd,ssh_updated,cmd,expected_log",
        (
            (
                True,
                True,
                ["systemctl", "restart", "ssh"],
                "Restarted the SSH daemon.",
            ),
            (
                True,
                False,
                ["systemctl", "status", "ssh"],
                "No need to restart SSH",
            ),
            (
                False,
                True,
                ["service", "ssh", "restart"],
                "Restarted the SSH daemon.",
            ),
            (
                False,
                False,
                ["service", "ssh", "status"],
                "No need to restart SSH",
            ),
        ),
    )
    @mock.patch(MODPATH + "update_ssh_config")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_restart_ssh_only_when_changes_made_and_ssh_installed(
        self,
        m_subp,
        update_ssh_config,
        uses_systemd,
        ssh_updated,
        cmd,
        expected_log,
        caplog,
    ):
        update_ssh_config.return_value = ssh_updated
        cloud = get_cloud("ubuntu")
        with mock.patch.object(
            cloud.distro, "uses_systemd", return_value=uses_systemd
        ):
            setpass.handle_ssh_pwauth(True, cloud.distro)
        if ssh_updated:
            m_subp.assert_called_with(cmd, capture=True)
        else:
            assert [mock.call(cmd, capture=True)] == m_subp.call_args_list
        assert expected_log in "\n".join(
            r.msg for r in caplog.records if r.levelname == "DEBUG"
        )

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_unchanged_value_does_nothing(
        self, m_subp, update_ssh_config, mock_uses_systemd
    ):
        """If 'unchanged', then no updates to config and no restart."""
        update_ssh_config.assert_not_called()
        cloud = get_cloud("ubuntu")
        setpass.handle_ssh_pwauth("unchanged", cloud.distro)
        assert [
            mock.call(["systemctl", "status", "ssh"], capture=True)
        ] == m_subp.call_args_list

    @pytest.mark.allow_subp_for("systemctl")
    @mock.patch("cloudinit.distros.subp.subp")
    def test_valid_value_changes_updates_ssh(self, m_subp, mock_uses_systemd):
        """If value is a valid changed value, then update will be called."""
        cloud = get_cloud("ubuntu")
        upname = MODPATH + "update_ssh_config"
        optname = "PasswordAuthentication"
        for n, value in enumerate(util.FALSE_STRINGS + util.TRUE_STRINGS, 1):
            optval = "yes" if value in util.TRUE_STRINGS else "no"
            with mock.patch(upname, return_value=False) as m_update:
                setpass.handle_ssh_pwauth(value, cloud.distro)
                assert (
                    mock.call({optname: optval}) == m_update.call_args_list[-1]
                )
                assert m_subp.call_count == n

    @pytest.mark.parametrize(
        [
            "uses_systemd",
            "raised_error",
            "warning_log",
            "debug_logs",
            "update_ssh_call_count",
        ],
        (
            (
                True,
                subp.ProcessExecutionError(
                    stderr="Service is not running.", exit_code=3
                ),
                None,
                [
                    "Writing config 'ssh_pwauth: True'. SSH service"
                    " 'ssh' will not be restarted because it is stopped.",
                    "Not restarting SSH service: service is stopped.",
                ],
                1,
            ),
            (
                True,
                subp.ProcessExecutionError(
                    stderr="Service is not installed.", exit_code=4
                ),
                "Ignoring config 'ssh_pwauth: True'. SSH service 'ssh' is"
                " not installed.",
                [],
                0,
            ),
            (
                True,
                subp.ProcessExecutionError(
                    stderr="Service is not available.", exit_code=2
                ),
                "Ignoring config 'ssh_pwauth: True'. SSH service 'ssh'"
                " is not available. Error: ",
                [],
                0,
            ),
            (
                False,
                subp.ProcessExecutionError(
                    stderr="Service is not available.", exit_code=25
                ),
                None,
                [
                    "Writing config 'ssh_pwauth: True'. SSH service"
                    " 'ssh' will not be restarted because it is not running"
                    " or not available.",
                    "Not restarting SSH service: service is stopped.",
                ],
                1,
            ),
            (
                False,
                subp.ProcessExecutionError(
                    stderr="Service is not available.", exit_code=3
                ),
                None,
                [
                    "Writing config 'ssh_pwauth: True'. SSH service"
                    " 'ssh' will not be restarted because it is not running"
                    " or not available.",
                    "Not restarting SSH service: service is stopped.",
                ],
                1,
            ),
            (
                False,
                subp.ProcessExecutionError(
                    stderr="Service is not available.", exit_code=4
                ),
                None,
                [
                    "Writing config 'ssh_pwauth: True'. SSH service"
                    " 'ssh' will not be restarted because it is not running"
                    " or not available.",
                    "Not restarting SSH service: service is stopped.",
                ],
                1,
            ),
        ),
    )
    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_no_restart_when_service_is_not_running(
        self,
        m_subp,
        m_update_ssh_config,
        uses_systemd,
        raised_error,
        warning_log,
        debug_logs,
        update_ssh_call_count,
        caplog,
    ):
        """Write config but don't restart SSH service when not running."""
        cloud = get_cloud("ubuntu")
        cloud.distro.manage_service = mock.Mock(side_effect=raised_error)
        cloud.distro.uses_systemd = mock.Mock(return_value=uses_systemd)

        setpass.handle_ssh_pwauth(True, cloud.distro)
        logs_by_level = {logging.WARNING: [], logging.DEBUG: []}
        for _, level, msg in caplog.record_tuples:
            logs_by_level[level].append(msg)
        if warning_log:
            assert warning_log in "\n".join(
                logs_by_level[logging.WARNING]
            ), logs_by_level
        for debug_log in debug_logs:
            assert debug_log in logs_by_level[logging.DEBUG]
        assert [
            mock.call("status", "ssh")
        ] == cloud.distro.manage_service.call_args_list
        assert m_update_ssh_config.call_count == update_ssh_call_count
        assert m_subp.call_count == 0
        assert cloud.distro.uses_systemd.call_count == 1


@pytest.mark.usefixtures("mock_uses_systemd")
class TestSetPasswordsHandle(CiTestCase):
    """Test cc_set_passwords.handle"""

    with_logs = True

    @mock.patch(MODPATH + "subp.subp")
    def test_handle_on_empty_config(self, m_subp):
        """handle logs that no password has changed when config is empty."""
        cloud = self.tmp_cloud(distro="ubuntu")
        setpass.handle(
            "IGNORED", cfg={}, cloud=cloud, log=self.logger, args=[]
        )
        self.assertEqual(
            "DEBUG: Leaving SSH config 'PasswordAuthentication' unchanged. "
            "ssh_pwauth=None\n",
            self.logs.getvalue(),
        )
        self.assertEqual(
            [mock.call(["systemctl", "status", "ssh"], capture=True)],
            m_subp.call_args_list,
        )

    @mock.patch(MODPATH + "subp.subp")
    def test_handle_on_chpasswd_list_parses_common_hashes(self, m_subp):
        """handle parses command password hashes."""
        cloud = self.tmp_cloud(distro="ubuntu")
        valid_hashed_pwds = [
            "root:$2y$10$8BQjxjVByHA/Ee.O1bCXtO8S7Y5WojbXWqnqYpUW.BrPx/"
            "Dlew1Va",
            "ubuntu:$6$5hOurLPO$naywm3Ce0UlmZg9gG2Fl9acWCVEoakMMC7dR52q"
            "SDexZbrN9z8yHxhUM2b.sxpguSwOlbOQSW/HpXazGGx3oo1",
        ]
        cfg = {"chpasswd": {"list": valid_hashed_pwds}}
        with mock.patch.object(setpass, "chpasswd") as chpasswd:
            setpass.handle(
                "IGNORED", cfg=cfg, cloud=cloud, log=self.logger, args=[]
            )
        self.assertIn(
            "DEBUG: Handling input for chpasswd as list.", self.logs.getvalue()
        )
        self.assertIn(
            "DEBUG: Setting hashed password for ['root', 'ubuntu']",
            self.logs.getvalue(),
        )
        valid = "\n".join(valid_hashed_pwds) + "\n"
        called = chpasswd.call_args[0][1]
        self.assertEqual(valid, called)

    @mock.patch(MODPATH + "util.is_BSD", return_value=True)
    @mock.patch(MODPATH + "subp.subp")
    def test_bsd_calls_custom_pw_cmds_to_set_and_expire_passwords(
        self, m_subp, m_is_bsd
    ):
        """BSD don't use chpasswd"""
        cloud = get_cloud(distro="freebsd")
        valid_pwds = ["ubuntu:passw0rd"]
        cfg = {"chpasswd": {"list": valid_pwds}}
        with mock.patch.object(
            cloud.distro, "uses_systemd", return_value=False
        ):
            setpass.handle(
                "IGNORED", cfg=cfg, cloud=cloud, log=self.logger, args=[]
            )
        self.assertEqual(
            [
                mock.call(
                    ["pw", "usermod", "ubuntu", "-h", "0"],
                    data="passw0rd",
                    logstring="chpasswd for ubuntu",
                ),
                mock.call(["pw", "usermod", "ubuntu", "-p", "01-Jan-1970"]),
                mock.call(["service", "sshd", "status"], capture=True),
            ],
            m_subp.call_args_list,
        )

    @mock.patch(MODPATH + "util.multi_log")
    @mock.patch(MODPATH + "subp.subp")
    def test_handle_on_chpasswd_list_creates_random_passwords(
        self, m_subp, m_multi_log
    ):
        """handle parses command set random passwords."""
        cloud = self.tmp_cloud(distro="ubuntu")
        valid_random_pwds = ["root:R", "ubuntu:RANDOM"]
        cfg = {"chpasswd": {"expire": "false", "list": valid_random_pwds}}
        with mock.patch.object(setpass, "chpasswd") as chpasswd:
            setpass.handle(
                "IGNORED", cfg=cfg, cloud=cloud, log=self.logger, args=[]
            )
        self.assertIn(
            "DEBUG: Handling input for chpasswd as list.", self.logs.getvalue()
        )
        self.assertEqual(1, chpasswd.call_count)
        passwords, _ = chpasswd.call_args
        user_pass = {
            user: password
            for user, password in (
                line.split(":") for line in passwords[1].splitlines()
            )
        }

        self.assertEqual(1, m_multi_log.call_count)
        self.assertEqual(
            mock.call(mock.ANY, stderr=False, fallback_to_stdout=False),
            m_multi_log.call_args,
        )

        self.assertEqual(set(["root", "ubuntu"]), set(user_pass.keys()))
        written_lines = m_multi_log.call_args[0][0].splitlines()
        for password in user_pass.values():
            for line in written_lines:
                if password in line:
                    break
            else:
                self.fail("Password not emitted to console")


class TestSetPasswordsSchema:
    @pytest.mark.parametrize(
        "config, error_msg",
        [
            # Test both formats still work
            ({"ssh_pwauth": True}, None),
            ({"ssh_pwauth": "yes"}, None),
            ({"ssh_pwauth": "unchanged"}, None),
            ({"chpasswd": {"list": "blah"}}, None),
            # Test regex
            ({"chpasswd": {"list": ["user:pass"]}}, None),
            # Test valid
            ({"password": "pass"}, None),
            # Test invalid values
            (
                {"chpasswd": {"expire": "yes"}},
                "'yes' is not of type 'boolean'",
            ),
            ({"chpasswd": {"list": ["user"]}}, ""),
            ({"chpasswd": {"list": []}}, r"\[\] is too short"),
        ],
    )
    @skipUnlessJsonSchema()
    def test_schema_validation(self, config, error_msg):
        if error_msg is None:
            validate_cloudconfig_schema(config, get_schema(), strict=True)
        else:
            with pytest.raises(SchemaValidationError, match=error_msg):
                validate_cloudconfig_schema(config, get_schema(), strict=True)


# vi: ts=4 expandtab
