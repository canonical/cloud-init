from unittest import mock

import pytest

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure
from cloudinit.subp import SubpResult


class TestAptKey:
    """TestAptKey
    Class to test apt-key commands
    """

    @mock.patch.object(subp, "subp", return_value=SubpResult("fakekey", ""))
    @mock.patch.object(util, "write_file")
    def _apt_key_add_success_helper(
        self, directory, gpg, *args, hardened=False
    ):
        file = cc_apt_configure.apt_key(
            "add",
            gpg=gpg,
            output_file="my-key",
            data="fakekey",
            hardened=hardened,
        )
        assert file == directory + "/my-key.gpg"

    def test_apt_key_add_success(self, m_gpg):
        """Verify the right directory path gets returned for unhardened case"""
        self._apt_key_add_success_helper("/etc/apt/trusted.gpg.d", m_gpg)

    def test_apt_key_add_success_hardened(self, m_gpg):
        """Verify the right directory path gets returned for hardened case"""
        self._apt_key_add_success_helper(
            "/etc/apt/cloud-init.gpg.d", m_gpg, hardened=True
        )

    def test_apt_key_add_fail_no_file_name(self, m_gpg):
        """Verify that null filename gets handled correctly"""
        file = cc_apt_configure.apt_key(
            "add", gpg=m_gpg, output_file=None, data=""
        )
        assert "/dev/null" == file

    def _apt_key_fail_helper(self, m_gpg):
        file = cc_apt_configure.apt_key(
            "add", gpg=m_gpg, output_file="my-key", data="fakekey"
        )
        assert file == "/dev/null"

    def test_apt_key_add_fail_no_file_name_subproc(self, m_gpg):
        """Verify that bad key value gets handled correctly"""
        m_gpg.dearmor = mock.Mock(side_effect=subp.ProcessExecutionError)
        self._apt_key_fail_helper(m_gpg)

    def test_apt_key_add_fail_no_file_name_unicode(self, m_gpg):
        """Verify that bad key encoding gets handled correctly"""
        m_gpg.dearmor = mock.Mock(
            side_effect=UnicodeDecodeError("test", b"", 1, 1, "")
        )
        self._apt_key_fail_helper(m_gpg)

    @pytest.mark.parametrize("command", ["list", "finger"])
    def test_apt_key_unsupported_command(self, command, m_gpg):
        """Only 'add' is supported, listing keys was removed as unused"""
        with pytest.raises(ValueError, match="only supports the 'add'"):
            cc_apt_configure.apt_key(command, m_gpg)
