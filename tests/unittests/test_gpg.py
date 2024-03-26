import os
from unittest import mock

import pytest

from cloudinit import gpg, subp
from cloudinit.subp import SubpResult

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


@pytest.fixture()
def m_subp():
    with mock.patch.object(
        gpg.subp, "subp", return_value=SubpResult("", "")
    ) as m_subp, mock.patch.object(gpg.time, "sleep"):
        yield m_subp


@pytest.fixture()
def m_which():
    with mock.patch.object(gpg.subp, "which") as m_which:
        yield m_which


@pytest.fixture()
def m_sleep():
    with mock.patch("cloudinit.gpg.time.sleep") as sleep:
        yield sleep


class TestGPGCommands:
    def test_dearmor_bad_value(self):
        """This exception is handled by the callee. Ensure it is not caught
        internally.
        """
        gpg_instance = gpg.GPG()
        with mock.patch.object(
            subp, "subp", side_effect=subp.ProcessExecutionError
        ):
            with pytest.raises(subp.ProcessExecutionError):
                gpg_instance.dearmor("garbage key value")

    def test_gpg_list_args(self, m_subp):
        """Verify correct command gets called to list keys"""
        gpg_instance = gpg.GPG()
        no_colons = [
            "gpg",
            "--no-options",
            "--with-fingerprint",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
            "key",
        ]
        colons = [
            "gpg",
            "--no-options",
            "--with-fingerprint",
            "--no-default-keyring",
            "--list-keys",
            "--keyring",
            "--with-colons",
            "key",
        ]
        gpg_instance.list_keys("key")
        assert (
            mock.call(colons, capture=True, update_env=gpg_instance.env)
            == m_subp.call_args
        )

        gpg_instance = gpg.GPG()
        gpg_instance.list_keys("key", human_output=True)
        assert m_subp.call_args == mock.call(
            no_colons, capture=True, update_env=gpg_instance.env
        )

    def test_gpg_dearmor_args(self, m_subp):
        """Verify correct command gets called to dearmor keys"""
        gpg_instance = gpg.GPG()
        gpg_instance.dearmor("key")
        test_call = mock.call(
            ["gpg", "--dearmor"],
            data="key",
            decode=False,
            update_env=gpg_instance.env,
        )
        assert test_call == m_subp.call_args


class TestReceiveKeys:
    """Test the recv_key method."""

    def test_retries_on_subp_exc(self, m_subp, m_sleep):
        """retry should be done on gpg receive keys failure."""
        gpg_instance = gpg.GPG()
        retries = (1, 2, 4)
        my_exc = subp.ProcessExecutionError(
            stdout="", stderr="", exit_code=2, cmd=["mycmd"]
        )
        m_subp.side_effect = (my_exc, my_exc, ("", ""))
        gpg_instance.recv_key("ABCD", "keyserver.example.com", retries=retries)
        assert [mock.call(1), mock.call(2)], m_sleep.call_args_list

    def test_raises_error_after_retries(self, m_subp, m_sleep):
        """If the final run fails, error should be raised."""
        gpg_instance = gpg.GPG()
        naplen = 1
        keyid, keyserver = ("ABCD", "keyserver.example.com")
        m_subp.side_effect = subp.ProcessExecutionError(
            stdout="", stderr="", exit_code=2, cmd=["mycmd"]
        )
        with pytest.raises(
            ValueError, match=f"{keyid}.*{keyserver}|{keyserver}.*{keyid}"
        ):
            gpg_instance.recv_key(keyid, keyserver, retries=(naplen,))
        m_sleep.assert_called_once()

    def test_no_retries_on_none(self, m_subp, m_sleep):
        """retry should not be done if retries is None."""
        gpg_instance = gpg.GPG()
        m_subp.side_effect = subp.ProcessExecutionError(
            stdout="", stderr="", exit_code=2, cmd=["mycmd"]
        )
        with pytest.raises(ValueError):
            gpg_instance.recv_key(
                "ABCD", "keyserver.example.com", retries=None
            )
        m_sleep.assert_not_called()

    def test_expected_gpg_command(self, m_subp, m_sleep):
        """Verify gpg is called with expected args."""
        gpg_instance = gpg.GPG()
        key, keyserver = ("DEADBEEF", "keyserver.example.com")
        retries = (1, 2, 4)
        m_subp.return_value = ("", "")
        gpg_instance.recv_key(key, keyserver, retries=retries)
        m_subp.assert_called_once_with(
            [
                "gpg",
                "--no-tty",
                "--keyserver=%s" % keyserver,
                "--recv-keys",
                key,
            ],
            capture=True,
            update_env=gpg_instance.env,
        )
        m_sleep.assert_not_called()

    def test_kill_gpg_succeeds(self, m_subp, m_which):
        """ensure that when gpgconf isn't found, processes are manually
        cleaned up. Also test that the context manager does cleanup

        """
        m_which.return_value = True
        with pytest.raises(ZeroDivisionError):
            with gpg.GPG() as gpg_context:

                # run a gpg command so that we have "started" gpg
                gpg_context.list_keys("")
                1 / 0  # pylint: disable=pointless-statement
        m_subp.assert_has_calls(
            [
                mock.call(
                    ["gpgconf", "--kill", "all"],
                    capture=True,
                    update_env=gpg_context.env,
                )
            ]
        )
        assert not os.path.isdir(str(gpg_context.temp_dir))

    def test_do_not_kill_unstarted_gpg(self, m_subp):
        """ensure that when gpg isn't started, gpg isn't killed, but the
        directory is cleaned up.
        """
        with pytest.raises(ZeroDivisionError):
            with gpg.GPG() as gpg_context:
                1 / 0  # pylint: disable=pointless-statement
        m_subp.assert_not_called()
        assert not os.path.isdir(str(gpg_context.temp_dir))

    def test_kill_gpg_failover_succeeds(self, m_subp, m_which):
        """ensure that when gpgconf isn't found, processes are manually
        cleaned up
        """
        m_which.return_value = None
        gpg_instance = gpg.GPG()

        # "start" gpg (if we don't, we won't kill gpg)
        gpg_instance.recv_key("", "")
        gpg_instance.kill_gpg()
        m_subp.assert_has_calls(
            [
                mock.call(
                    [
                        "ps",
                        "-o",
                        "ppid,pid",
                        "-C",
                        "keyboxd",
                        "-C",
                        "dirmngr",
                        "-C",
                        "gpg-agent",
                    ],
                    capture=True,
                    rcs=[0, 1],
                )
            ]
        )
