# This file is part of cloud-init. See LICENSE file for license information.
"""Test gpg module."""

from cloudinit import gpg
from cloudinit import util
from cloudinit.tests.helpers import CiTestCase

import mock


@mock.patch("cloudinit.gpg.time.sleep")
@mock.patch("cloudinit.gpg.util.subp")
class TestReceiveKeys(CiTestCase):
    """Test the recv_key method."""

    def test_retries_on_subp_exc(self, m_subp, m_sleep):
        """retry should be done on gpg receive keys failure."""
        retries = (1, 2, 4)
        my_exc = util.ProcessExecutionError(
            stdout='', stderr='', exit_code=2, cmd=['mycmd'])
        m_subp.side_effect = (my_exc, my_exc, ('', ''))
        gpg.recv_key("ABCD", "keyserver.example.com", retries=retries)
        self.assertEqual([mock.call(1), mock.call(2)], m_sleep.call_args_list)

    def test_raises_error_after_retries(self, m_subp, m_sleep):
        """If the final run fails, error should be raised."""
        naplen = 1
        keyid, keyserver = ("ABCD", "keyserver.example.com")
        m_subp.side_effect = util.ProcessExecutionError(
            stdout='', stderr='', exit_code=2, cmd=['mycmd'])
        with self.assertRaises(ValueError) as rcm:
            gpg.recv_key(keyid, keyserver, retries=(naplen,))
        self.assertIn(keyid, str(rcm.exception))
        self.assertIn(keyserver, str(rcm.exception))
        m_sleep.assert_called_with(naplen)

    def test_no_retries_on_none(self, m_subp, m_sleep):
        """retry should not be done if retries is None."""
        m_subp.side_effect = util.ProcessExecutionError(
            stdout='', stderr='', exit_code=2, cmd=['mycmd'])
        with self.assertRaises(ValueError):
            gpg.recv_key("ABCD", "keyserver.example.com", retries=None)
        m_sleep.assert_not_called()

    def test_expected_gpg_command(self, m_subp, m_sleep):
        """Verify gpg is called with expected args."""
        key, keyserver = ("DEADBEEF", "keyserver.example.com")
        retries = (1, 2, 4)
        m_subp.return_value = ('', '')
        gpg.recv_key(key, keyserver, retries=retries)
        m_subp.assert_called_once_with(
            ['gpg', '--keyserver=%s' % keyserver, '--recv-keys', key],
            capture=True)
        m_sleep.assert_not_called()
