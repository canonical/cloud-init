# This file is part of cloud-init. See LICENSE file for license information.

from unittest import mock

from cloudinit.config import cc_set_passwords as setpass
from cloudinit.tests.helpers import CiTestCase
from cloudinit import util

MODPATH = "cloudinit.config.cc_set_passwords."


class TestHandleSshPwauth(CiTestCase):
    """Test cc_set_passwords handling of ssh_pwauth in handle_ssh_pwauth."""

    with_logs = True

    @mock.patch(MODPATH + "subp.subp")
    def test_unknown_value_logs_warning(self, m_subp):
        setpass.handle_ssh_pwauth("floo")
        self.assertIn("Unrecognized value: ssh_pwauth=floo",
                      self.logs.getvalue())
        m_subp.assert_not_called()

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "subp.subp")
    def test_systemctl_as_service_cmd(self, m_subp, m_update_ssh_config):
        """If systemctl in service cmd: systemctl restart name."""
        setpass.handle_ssh_pwauth(
            True, service_cmd=["systemctl"], service_name="myssh")
        self.assertEqual(mock.call(["systemctl", "restart", "myssh"]),
                         m_subp.call_args)

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "subp.subp")
    def test_service_as_service_cmd(self, m_subp, m_update_ssh_config):
        """If systemctl in service cmd: systemctl restart name."""
        setpass.handle_ssh_pwauth(
            True, service_cmd=["service"], service_name="myssh")
        self.assertEqual(mock.call(["service", "myssh", "restart"]),
                         m_subp.call_args)

    @mock.patch(MODPATH + "update_ssh_config", return_value=False)
    @mock.patch(MODPATH + "subp.subp")
    def test_not_restarted_if_not_updated(self, m_subp, m_update_ssh_config):
        """If config is not updated, then no system restart should be done."""
        setpass.handle_ssh_pwauth(True)
        m_subp.assert_not_called()
        self.assertIn("No need to restart SSH", self.logs.getvalue())

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "subp.subp")
    def test_unchanged_does_nothing(self, m_subp, m_update_ssh_config):
        """If 'unchanged', then no updates to config and no restart."""
        setpass.handle_ssh_pwauth(
            "unchanged", service_cmd=["systemctl"], service_name="myssh")
        m_update_ssh_config.assert_not_called()
        m_subp.assert_not_called()

    @mock.patch(MODPATH + "subp.subp")
    def test_valid_change_values(self, m_subp):
        """If value is a valid changen value, then update should be called."""
        upname = MODPATH + "update_ssh_config"
        optname = "PasswordAuthentication"
        for value in util.FALSE_STRINGS + util.TRUE_STRINGS:
            optval = "yes" if value in util.TRUE_STRINGS else "no"
            with mock.patch(upname, return_value=False) as m_update:
                setpass.handle_ssh_pwauth(value)
                m_update.assert_called_with({optname: optval})
        m_subp.assert_not_called()


class TestSetPasswordsHandle(CiTestCase):
    """Test cc_set_passwords.handle"""

    with_logs = True

    def test_handle_on_empty_config(self, *args):
        """handle logs that no password has changed when config is empty."""
        cloud = self.tmp_cloud(distro='ubuntu')
        setpass.handle(
            'IGNORED', cfg={}, cloud=cloud, log=self.logger, args=[])
        self.assertEqual(
            "DEBUG: Leaving SSH config 'PasswordAuthentication' unchanged. "
            'ssh_pwauth=None\n',
            self.logs.getvalue())

    @mock.patch(MODPATH + "subp.subp")
    def test_handle_on_chpasswd_list_parses_common_hashes(self, m_subp):
        """handle parses command password hashes."""
        cloud = self.tmp_cloud(distro='ubuntu')
        valid_hashed_pwds = [
            'root:$2y$10$8BQjxjVByHA/Ee.O1bCXtO8S7Y5WojbXWqnqYpUW.BrPx/'
            'Dlew1Va',
            'ubuntu:$6$5hOurLPO$naywm3Ce0UlmZg9gG2Fl9acWCVEoakMMC7dR52q'
            'SDexZbrN9z8yHxhUM2b.sxpguSwOlbOQSW/HpXazGGx3oo1']
        cfg = {'chpasswd': {'list': valid_hashed_pwds}}
        with mock.patch(MODPATH + 'subp.subp') as m_subp:
            setpass.handle(
                'IGNORED', cfg=cfg, cloud=cloud, log=self.logger, args=[])
        self.assertIn(
            'DEBUG: Handling input for chpasswd as list.',
            self.logs.getvalue())
        self.assertIn(
            "DEBUG: Setting hashed password for ['root', 'ubuntu']",
            self.logs.getvalue())
        self.assertEqual(
            [mock.call(['chpasswd', '-e'],
             '\n'.join(valid_hashed_pwds) + '\n')],
            m_subp.call_args_list)

    @mock.patch(MODPATH + "util.is_BSD")
    @mock.patch(MODPATH + "subp.subp")
    def test_bsd_calls_custom_pw_cmds_to_set_and_expire_passwords(
            self, m_subp, m_is_bsd):
        """BSD don't use chpasswd"""
        m_is_bsd.return_value = True
        cloud = self.tmp_cloud(distro='freebsd')
        valid_pwds = ['ubuntu:passw0rd']
        cfg = {'chpasswd': {'list': valid_pwds}}
        setpass.handle(
            'IGNORED', cfg=cfg, cloud=cloud, log=self.logger, args=[])
        self.assertEqual([
            mock.call(['pw', 'usermod', 'ubuntu', '-h', '0'], data='passw0rd',
                      logstring="chpasswd for ubuntu"),
            mock.call(['pw', 'usermod', 'ubuntu', '-p', '01-Jan-1970'])],
            m_subp.call_args_list)

    @mock.patch(MODPATH + "util.multi_log")
    @mock.patch(MODPATH + "util.is_BSD")
    @mock.patch(MODPATH + "subp.subp")
    def test_handle_on_chpasswd_list_creates_random_passwords(
        self, m_subp, m_is_bsd, m_multi_log
    ):
        """handle parses command set random passwords."""
        m_is_bsd.return_value = False
        cloud = self.tmp_cloud(distro='ubuntu')
        valid_random_pwds = [
            'root:R',
            'ubuntu:RANDOM']
        cfg = {'chpasswd': {'expire': 'false', 'list': valid_random_pwds}}
        with mock.patch(MODPATH + 'subp.subp') as m_subp:
            setpass.handle(
                'IGNORED', cfg=cfg, cloud=cloud, log=self.logger, args=[])
        self.assertIn(
            'DEBUG: Handling input for chpasswd as list.',
            self.logs.getvalue())

        self.assertEqual(1, m_subp.call_count)
        args, _kwargs = m_subp.call_args
        self.assertEqual(["chpasswd"], args[0])

        stdin = args[1]
        user_pass = {
            user: password
            for user, password
            in (line.split(":") for line in stdin.splitlines())
        }

        self.assertEqual(1, m_multi_log.call_count)
        self.assertEqual(
            mock.call(mock.ANY, stderr=False, fallback_to_stdout=False),
            m_multi_log.call_args
        )

        self.assertEqual(set(["root", "ubuntu"]), set(user_pass.keys()))
        written_lines = m_multi_log.call_args[0][0].splitlines()
        for password in user_pass.values():
            for line in written_lines:
                if password in line:
                    break
            else:
                self.fail("Password not emitted to console")


# vi: ts=4 expandtab
