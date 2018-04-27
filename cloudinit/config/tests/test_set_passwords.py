# This file is part of cloud-init. See LICENSE file for license information.

import mock

from cloudinit.config import cc_set_passwords as setpass
from cloudinit.tests.helpers import CiTestCase
from cloudinit import util

MODPATH = "cloudinit.config.cc_set_passwords."


class TestHandleSshPwauth(CiTestCase):
    """Test cc_set_passwords handling of ssh_pwauth in handle_ssh_pwauth."""

    with_logs = True

    @mock.patch(MODPATH + "util.subp")
    def test_unknown_value_logs_warning(self, m_subp):
        setpass.handle_ssh_pwauth("floo")
        self.assertIn("Unrecognized value: ssh_pwauth=floo",
                      self.logs.getvalue())
        m_subp.assert_not_called()

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "util.subp")
    def test_systemctl_as_service_cmd(self, m_subp, m_update_ssh_config):
        """If systemctl in service cmd: systemctl restart name."""
        setpass.handle_ssh_pwauth(
            True, service_cmd=["systemctl"], service_name="myssh")
        self.assertEqual(mock.call(["systemctl", "restart", "myssh"]),
                         m_subp.call_args)

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "util.subp")
    def test_service_as_service_cmd(self, m_subp, m_update_ssh_config):
        """If systemctl in service cmd: systemctl restart name."""
        setpass.handle_ssh_pwauth(
            True, service_cmd=["service"], service_name="myssh")
        self.assertEqual(mock.call(["service", "myssh", "restart"]),
                         m_subp.call_args)

    @mock.patch(MODPATH + "update_ssh_config", return_value=False)
    @mock.patch(MODPATH + "util.subp")
    def test_not_restarted_if_not_updated(self, m_subp, m_update_ssh_config):
        """If config is not updated, then no system restart should be done."""
        setpass.handle_ssh_pwauth(True)
        m_subp.assert_not_called()
        self.assertIn("No need to restart ssh", self.logs.getvalue())

    @mock.patch(MODPATH + "update_ssh_config", return_value=True)
    @mock.patch(MODPATH + "util.subp")
    def test_unchanged_does_nothing(self, m_subp, m_update_ssh_config):
        """If 'unchanged', then no updates to config and no restart."""
        setpass.handle_ssh_pwauth(
            "unchanged", service_cmd=["systemctl"], service_name="myssh")
        m_update_ssh_config.assert_not_called()
        m_subp.assert_not_called()

    @mock.patch(MODPATH + "util.subp")
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

# vi: ts=4 expandtab
