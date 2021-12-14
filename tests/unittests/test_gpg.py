from unittest import mock

import pytest

from cloudinit import gpg, subp
from tests.unittests.helpers import CiTestCase

TEST_KEY_HUMAN = """
/etc/apt/cloud-init.gpg.d/my_key.gpg
--------------------------------------------
pub   rsa4096 2021-10-22 [SC]
      3A3E F34D FDED B3B7 F3FD  F603 F83F 7712 9A5E BD85
uid           [ unknown] Brett Holman <brett.holman@canonical.com>
sub   rsa4096 2021-10-22 [A]
sub   rsa4096 2021-10-22 [E]
"""

TEST_KEY_MACHINE = """
tru::1:1635129362:0:3:1:5
pub:-:4096:1:F83F77129A5EBD85:1634912922:::-:::scESCA::::::23::0:
fpr:::::::::3A3EF34DFDEDB3B7F3FDF603F83F77129A5EBD85:
uid:-::::1634912922::64F1F1D6FA96316752D635D7C6406C52C40713C7::Brett Holman \
<brett.holman@canonical.com>::::::::::0:
sub:-:4096:1:544B39C9A9141F04:1634912922::::::a::::::23:
fpr:::::::::8BD901490D6EC986D03D6F0D544B39C9A9141F04:
sub:-:4096:1:F45D9443F0A87092:1634912922::::::e::::::23:
fpr:::::::::8CCCB332317324F030A45B19F45D9443F0A87092:
"""

TEST_KEY_FINGERPRINT_HUMAN = (
    "3A3E F34D FDED B3B7 F3FD  F603 F83F 7712 9A5E BD85"
)

TEST_KEY_FINGERPRINT_MACHINE = "3A3EF34DFDEDB3B7F3FDF603F83F77129A5EBD85"


class TestGPGCommands:
    def test_dearmor_bad_value(self):
        """This exception is handled by the callee. Ensure it is not caught
        internally.
        """
        with mock.patch.object(
            subp, "subp", side_effect=subp.ProcessExecutionError
        ):
            with pytest.raises(subp.ProcessExecutionError):
                gpg.dearmor("garbage key value")

    def test_gpg_list_args(self):
        """Verify correct command gets called to list keys"""
        no_colons = [
            "gpg",
            "--with-fingerprint",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
            "key",
        ]
        colons = [
            "gpg",
            "--with-fingerprint",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
            "--with-colons",
            "key",
        ]
        with mock.patch.object(subp, "subp", return_value=("", "")) as m_subp:
            gpg.list("key")
            assert mock.call(colons, capture=True) == m_subp.call_args

            gpg.list("key", human_output=True)
            test_calls = mock.call((no_colons), capture=True)
            assert test_calls == m_subp.call_args

    def test_gpg_dearmor_args(self):
        """Verify correct command gets called to dearmor keys"""
        with mock.patch.object(subp, "subp", return_value=("", "")) as m_subp:
            gpg.dearmor("key")
            test_call = mock.call(
                ["gpg", "--dearmor"], data="key", decode=False
            )
            assert test_call == m_subp.call_args

    @mock.patch("cloudinit.gpg.time.sleep")
    @mock.patch("cloudinit.gpg.subp.subp")
    class TestReceiveKeys(CiTestCase):
        """Test the recv_key method."""

        def test_retries_on_subp_exc(self, m_subp, m_sleep):
            """retry should be done on gpg receive keys failure."""
            retries = (1, 2, 4)
            my_exc = subp.ProcessExecutionError(
                stdout="", stderr="", exit_code=2, cmd=["mycmd"]
            )
            m_subp.side_effect = (my_exc, my_exc, ("", ""))
            gpg.recv_key("ABCD", "keyserver.example.com", retries=retries)
            self.assertEqual(
                [mock.call(1), mock.call(2)], m_sleep.call_args_list
            )

        def test_raises_error_after_retries(self, m_subp, m_sleep):
            """If the final run fails, error should be raised."""
            naplen = 1
            keyid, keyserver = ("ABCD", "keyserver.example.com")
            m_subp.side_effect = subp.ProcessExecutionError(
                stdout="", stderr="", exit_code=2, cmd=["mycmd"]
            )
            with self.assertRaises(ValueError) as rcm:
                gpg.recv_key(keyid, keyserver, retries=(naplen,))
            self.assertIn(keyid, str(rcm.exception))
            self.assertIn(keyserver, str(rcm.exception))
            m_sleep.assert_called_with(naplen)

        def test_no_retries_on_none(self, m_subp, m_sleep):
            """retry should not be done if retries is None."""
            m_subp.side_effect = subp.ProcessExecutionError(
                stdout="", stderr="", exit_code=2, cmd=["mycmd"]
            )
            with self.assertRaises(ValueError):
                gpg.recv_key("ABCD", "keyserver.example.com", retries=None)
            m_sleep.assert_not_called()

        def test_expected_gpg_command(self, m_subp, m_sleep):
            """Verify gpg is called with expected args."""
            key, keyserver = ("DEADBEEF", "keyserver.example.com")
            retries = (1, 2, 4)
            m_subp.return_value = ("", "")
            gpg.recv_key(key, keyserver, retries=retries)
            m_subp.assert_called_once_with(
                [
                    "gpg",
                    "--no-tty",
                    "--keyserver=%s" % keyserver,
                    "--recv-keys",
                    key,
                ],
                capture=True,
            )
            m_sleep.assert_not_called()
