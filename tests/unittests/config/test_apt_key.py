import os
from unittest import mock

from cloudinit import subp, util
from cloudinit.config import cc_apt_configure

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


class TestAptKey:
    """TestAptKey
    Class to test apt-key commands
    """

    @mock.patch.object(subp, "subp", return_value=("fakekey", ""))
    @mock.patch.object(util, "write_file")
    def _apt_key_add_success_helper(self, directory, *args, hardened=False):
        file = cc_apt_configure.apt_key(
            "add", output_file="my-key", data="fakekey", hardened=hardened
        )
        assert file == directory + "/my-key.gpg"

    def test_apt_key_add_success(self):
        """Verify the right directory path gets returned for unhardened case"""
        self._apt_key_add_success_helper("/etc/apt/trusted.gpg.d")

    def test_apt_key_add_success_hardened(self):
        """Verify the right directory path gets returned for hardened case"""
        self._apt_key_add_success_helper(
            "/etc/apt/cloud-init.gpg.d", hardened=True
        )

    def test_apt_key_add_fail_no_file_name(self):
        """Verify that null filename gets handled correctly"""
        file = cc_apt_configure.apt_key("add", output_file=None, data="")
        assert "/dev/null" == file

    def _apt_key_fail_helper(self):
        file = cc_apt_configure.apt_key(
            "add", output_file="my-key", data="fakekey"
        )
        assert file == "/dev/null"

    @mock.patch.object(subp, "subp", side_effect=subp.ProcessExecutionError)
    def test_apt_key_add_fail_no_file_name_subproc(self, *args):
        """Verify that bad key value gets handled correctly"""
        self._apt_key_fail_helper()

    @mock.patch.object(
        subp, "subp", side_effect=UnicodeDecodeError("test", b"", 1, 1, "")
    )
    def test_apt_key_add_fail_no_file_name_unicode(self, *args):
        """Verify that bad key encoding gets handled correctly"""
        self._apt_key_fail_helper()

    def _apt_key_list_success_helper(self, finger, key, human_output=True):
        @mock.patch.object(os, "listdir", return_value=("/fake/dir/key.gpg",))
        @mock.patch.object(subp, "subp", return_value=(key, ""))
        def mocked_list(*a):

            keys = cc_apt_configure.apt_key("list", human_output)
            assert finger in keys

        mocked_list()

    def test_apt_key_list_success_human(self):
        """Verify expected key output, human"""
        self._apt_key_list_success_helper(
            TEST_KEY_FINGERPRINT_HUMAN, TEST_KEY_HUMAN
        )

    def test_apt_key_list_success_machine(self):
        """Verify expected key output, machine"""
        self._apt_key_list_success_helper(
            TEST_KEY_FINGERPRINT_MACHINE, TEST_KEY_MACHINE, human_output=False
        )

    @mock.patch.object(os, "listdir", return_value=())
    @mock.patch.object(subp, "subp", return_value=("", ""))
    def test_apt_key_list_fail_no_keys(self, *args):
        """Ensure falsy output for no keys"""
        keys = cc_apt_configure.apt_key("list")
        assert not keys

    @mock.patch.object(os, "listdir", return_value="file_not_gpg_key.txt")
    @mock.patch.object(subp, "subp", return_value=("", ""))
    def test_apt_key_list_fail_no_keys_file(self, *args):
        """Ensure non-gpg file is not returned.

        apt-key used file extensions for this, so we do too
        """
        assert not cc_apt_configure.apt_key("list")

    @mock.patch.object(subp, "subp", side_effect=subp.ProcessExecutionError)
    @mock.patch.object(os, "listdir", return_value="bad_gpg_key.gpg")
    def test_apt_key_list_fail_bad_key_file(self, *args):
        """Ensure bad gpg key doesn't throw exeption."""
        assert not cc_apt_configure.apt_key("list")
