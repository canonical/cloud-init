import os
from unittest import mock

import pytest

from cloudinit import gpg, subp
from cloudinit.subp import SubpResult


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
                gpg_context.dearmor("")
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
