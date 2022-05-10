# This file is part of cloud-init. See LICENSE file for license information.

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

MODPATH = "cloudinit.config.cc_set_passwords."


class TestHandleSshPwauth(CiTestCase):
    """Test cc_set_passwords handling of ssh_pwauth in handle_ssh_pwauth."""

    with_logs = True

    @mock.patch("cloudinit.distros.subp.subp")
    def test_unknown_value_logs_warning(self, m_subp):
        cloud = self.tmp_cloud(distro="ubuntu")
        setpass.handle_ssh_pwauth("floo", cloud.distro)
        self.assertIn(
            "Unrecognized value: ssh_pwauth=floo", self.logs.getvalue()
        )
        self.assertEqual(
            [mock.call(["systemctl", "status", "ssh"], capture=True)],
            m_subp.call_args_list,
        )

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_systemctl_as_service_cmd(self, m_subp, m_update_ssh_config):
        """If systemctl in service cmd: systemctl restart name."""
        cloud = self.tmp_cloud(distro="ubuntu")
        cloud.distro.init_cmd = ["systemctl"]
        setpass.handle_ssh_pwauth(True, cloud.distro)
        m_subp.assert_called_with(
            ["systemctl", "restart", "ssh"], capture=True
        )
        self.assertIn("DEBUG: Restarted the SSH daemon.", self.logs.getvalue())

    @mock.patch(MODPATH + "update_ssh_config", return_value=False)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_not_restarted_if_not_updated(self, m_subp, m_update_ssh_config):
        """If config is not updated, then no system restart should be done."""
        cloud = self.tmp_cloud(distro="ubuntu")
        setpass.handle_ssh_pwauth(True, cloud.distro)
        self.assertEqual(
            [mock.call(["systemctl", "status", "ssh"], capture=True)],
            m_subp.call_args_list,
        )
        self.assertIn("No need to restart SSH", self.logs.getvalue())

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_unchanged_does_nothing(self, m_subp, m_update_ssh_config):
        """If 'unchanged', then no updates to config and no restart."""
        cloud = self.tmp_cloud(distro="ubuntu")
        setpass.handle_ssh_pwauth("unchanged", cloud.distro)
        m_update_ssh_config.assert_not_called()
        self.assertEqual(m_update_ssh_config.call_count, 0)
        self.assertEqual(
            [mock.call(["systemctl", "status", "ssh"], capture=True)],
            m_subp.call_args_list,
        )

    @mock.patch("cloudinit.distros.subp.subp")
    def test_valid_change_values(self, m_subp):
        """If value is a valid changen value, then update should be called."""
        cloud = self.tmp_cloud(distro="ubuntu")
        upname = MODPATH + "update_ssh_config"
        optname = "PasswordAuthentication"
        for n, value in enumerate(util.FALSE_STRINGS + util.TRUE_STRINGS, 1):
            optval = "yes" if value in util.TRUE_STRINGS else "no"
            with mock.patch(upname, return_value=False) as m_update:
                setpass.handle_ssh_pwauth(value, cloud.distro)
                self.assertEqual(
                    mock.call({optname: optval}), m_update.call_args_list[-1]
                )
            self.assertEqual(m_subp.call_count, n)
        self.assertEqual(
            mock.call(["systemctl", "status", "ssh"], capture=True),
            m_subp.call_args_list[-1],
        )

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_failed_ssh_service_is_not_runing(
        self, m_subp, m_update_ssh_config
    ):
        """If the ssh service is not running, then the config is updated and
        no restart.
        """
        cloud = self.tmp_cloud(distro="ubuntu")
        cloud.distro.init_cmd = ["systemctl"]
        cloud.distro.manage_service = mock.Mock(
            side_effect=subp.ProcessExecutionError(
                stderr="Service is not running.", exit_code=3
            )
        )

        setpass.handle_ssh_pwauth(True, cloud.distro)
        self.assertIn(
            r"WARNING: Writing config 'ssh_pwauth: True'."
            r" SSH service 'ssh' will not be restarted because is stopped.",
            self.logs.getvalue(),
        )
        self.assertIn(
            r"DEBUG: Not restarting SSH service: service is stopped.",
            self.logs.getvalue(),
        )
        self.assertEqual(
            [mock.call("status", "ssh")],
            cloud.distro.manage_service.call_args_list,
        )
        self.assertEqual(m_update_ssh_config.call_count, 1)
        self.assertEqual(m_subp.call_count, 0)

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_failed_ssh_service_is_not_installed(
        self, m_subp, m_update_ssh_config
    ):
        """If the ssh service is not installed, then no updates config and
        no restart.
        """
        cloud = self.tmp_cloud(distro="ubuntu")
        cloud.distro.init_cmd = ["systemctl"]
        cloud.distro.manage_service = mock.Mock(
            side_effect=subp.ProcessExecutionError(
                stderr="Service is not installed.", exit_code=4
            )
        )

        setpass.handle_ssh_pwauth(True, cloud.distro)
        self.assertIn(
            r"WARNING: Ignoring config 'ssh_pwauth: True'."
            r" SSH service 'ssh' is not installed.",
            self.logs.getvalue(),
        )
        self.assertEqual(
            [mock.call("status", "ssh")],
            cloud.distro.manage_service.call_args_list,
        )
        self.assertEqual(m_update_ssh_config.call_count, 0)
        self.assertEqual(m_subp.call_count, 0)

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch("cloudinit.distros.subp.subp")
    def test_failed_ssh_service_is_not_available(
        self, m_subp, m_update_ssh_config
    ):
        """If the ssh service is not available, then no updates config and
        no restart.
        """
        cloud = self.tmp_cloud(distro="ubuntu")
        cloud.distro.init_cmd = ["systemctl"]
        process_error = "Service is not available."
        cloud.distro.manage_service = mock.Mock(
            side_effect=subp.ProcessExecutionError(
                stderr=process_error, exit_code=2
            )
        )

        setpass.handle_ssh_pwauth(True, cloud.distro)
        self.assertIn(
            r"WARNING: Ignoring config 'ssh_pwauth: True'."
            r" SSH service 'ssh' is not available. Error: ",
            self.logs.getvalue(),
        )
        self.assertIn(process_error, self.logs.getvalue())
        self.assertEqual(
            [mock.call("status", "ssh")],
            cloud.distro.manage_service.call_args_list,
        )
        self.assertEqual(m_update_ssh_config.call_count, 0)
        self.assertEqual(m_subp.call_count, 0)


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

    @mock.patch(MODPATH + "util.is_BSD")
    @mock.patch(MODPATH + "subp.subp")
    def test_bsd_calls_custom_pw_cmds_to_set_and_expire_passwords(
        self, m_subp, m_is_bsd
    ):
        """BSD don't use chpasswd"""
        m_is_bsd.return_value = True
        cloud = self.tmp_cloud(distro="freebsd")
        valid_pwds = ["ubuntu:passw0rd"]
        cfg = {"chpasswd": {"list": valid_pwds}}
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
                mock.call(["systemctl", "status", "sshd"], capture=True),
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
