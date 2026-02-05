# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.subp utility functions"""

import json
import logging
import os
import stat
import sys
from unittest import mock

import pytest

from cloudinit import subp, util
from tests.helpers import get_top_level_dir

SH = "sh"
BOGUS_COMMAND = "this-is-not-expected-to-be-a-program-name"


class TestPrependBaseCommands:

    def test_prepend_base_command_errors_on_neither_string_nor_list(self):
        """Raise an error for each command which is not a string or list."""
        orig_commands = ["ls", 1, {"not": "gonna work"}, ["basecmd", "list"]]
        with pytest.raises(
            TypeError,
            match="Invalid basecmd config. These commands are not a string or"
            " list:\n1\n{'not': 'gonna work'}",
        ):
            subp.prepend_base_command(
                base_command="basecmd", commands=orig_commands
            )

    def test_prepend_base_command_warns_on_non_base_string_commands(
        self, caplog
    ):
        """Warn on each non-base for commands of type string."""
        orig_commands = [
            "ls",
            "basecmd list",
            "touch /blah",
            "basecmd install x",
        ]
        fixed_commands = subp.prepend_base_command(
            base_command="basecmd", commands=orig_commands
        )
        assert (
            mock.ANY,
            logging.WARNING,
            "Non-basecmd commands in basecmd config:\nls\ntouch /blah",
        ) in caplog.record_tuples
        assert orig_commands == fixed_commands

    def test_prepend_base_command_prepends_on_non_base_list_commands(
        self, caplog
    ):
        """Prepend 'basecmd' for each non-basecmd command of type list."""
        orig_commands = [
            ["ls"],
            ["basecmd", "list"],
            ["basecmda", "/blah"],
            ["basecmd", "install", "x"],
        ]
        expected = [
            ["basecmd", "ls"],
            ["basecmd", "list"],
            ["basecmd", "basecmda", "/blah"],
            ["basecmd", "install", "x"],
        ]
        fixed_commands = subp.prepend_base_command(
            base_command="basecmd", commands=orig_commands
        )
        assert "" == caplog.text
        assert expected == fixed_commands

    def test_prepend_base_command_removes_first_item_when_none(self, caplog):
        """Remove the first element of a non-basecmd when it is None."""
        orig_commands = [
            [None, "ls"],
            ["basecmd", "list"],
            [None, "touch", "/blah"],
            ["basecmd", "install", "x"],
        ]
        expected = [
            ["ls"],
            ["basecmd", "list"],
            ["touch", "/blah"],
            ["basecmd", "install", "x"],
        ]
        fixed_commands = subp.prepend_base_command(
            base_command="basecmd", commands=orig_commands
        )
        assert "" == caplog.text
        assert expected == fixed_commands


@pytest.mark.allow_all_subp
class TestSubp:
    stdin2err = [SH, "-c", "cat >&2"]
    stdin2out = ["cat"]
    utf8_invalid = b"ab\xaadef"
    utf8_valid = b"start \xc3\xa9 end"
    utf8_valid_2 = b"d\xc3\xa9j\xc8\xa7"

    @staticmethod
    def printf_cmd(arg):
        """print with builtin printf"""
        return [SH, "-c", 'printf "$@"', "printf", arg]

    def test_subp_handles_bytestrings(self, tmp_path):
        """subp can run a bytestring command if shell is True."""
        tmp_file = str(tmp_path / "test.out")
        cmd = "echo HI MOM >> {tmp_file}".format(tmp_file=tmp_file)
        (out, _err) = subp.subp(cmd.encode("utf-8"), shell=True)
        assert "" == out
        assert "" == _err
        assert "HI MOM\n" == util.load_text_file(tmp_file)

    def test_subp_handles_strings(self, tmp_path):
        """subp can run a string command if shell is True."""
        tmp_file = str(tmp_path / "test.out")
        cmd = "echo HI MOM >> {tmp_file}".format(tmp_file=tmp_file)
        (out, _err) = subp.subp(cmd, shell=True)
        assert "" == out
        assert "" == _err
        assert "HI MOM\n" == util.load_text_file(tmp_file)

    def test_subp_handles_utf8(self):
        # The given bytes contain utf-8 accented characters as seen in e.g.
        # the "deja dup" package in Ubuntu.
        cmd = self.printf_cmd(self.utf8_valid_2)
        (out, _err) = subp.subp(cmd, capture=True)
        assert out == self.utf8_valid_2.decode("utf-8")

    def test_subp_respects_decode_false(self):
        (out, err) = subp.subp(
            self.stdin2out, capture=True, decode=False, data=self.utf8_valid
        )
        assert isinstance(out, bytes)
        assert isinstance(err, bytes)
        assert out == self.utf8_valid

    def test_subp_decode_ignore(self):
        """ensure that invalid utf-8 is ignored with the "ignore" kwarg"""
        # this executes a string that writes invalid utf-8 to stdout
        with mock.patch.object(
            subp.subprocess,
            "Popen",
            autospec=True,
        ) as sp:
            sp.return_value.communicate = mock.Mock(
                return_value=(b"abc\xaadef", None)
            )
            sp.return_value.returncode = 0
            assert (
                "abcdef"
                == subp.subp([SH], capture=True, decode="ignore").stdout
            )

    def test_subp_decode_strict_valid_utf8(self):
        (out, _err) = subp.subp(
            self.stdin2out, capture=True, decode="strict", data=self.utf8_valid
        )
        assert out == self.utf8_valid.decode("utf-8")

    def test_subp_decode_invalid_utf8_replaces(self):
        (out, _err) = subp.subp(
            self.stdin2out, capture=True, data=self.utf8_invalid
        )
        expected = self.utf8_invalid.decode("utf-8", "replace")
        assert out == expected

    def test_subp_decode_strict_raises(self):
        args = []
        kwargs = {
            "args": self.stdin2out,
            "capture": True,
            "decode": "strict",
            "data": self.utf8_invalid,
        }
        with pytest.raises(UnicodeDecodeError):
            subp.subp(*args, **kwargs)

    def test_subp_capture_stderr(self):
        data = b"hello world"
        (out, err) = subp.subp(
            self.stdin2err,
            capture=True,
            decode=False,
            data=data,
            update_env={"LC_ALL": "C"},
        )
        assert err == data
        assert out == b""

    def test_subp_reads_env(self):
        with mock.patch.dict("os.environ", values={"FOO": "BAR"}):
            assert {"FOO=BAR"}.issubset(
                subp.subp("env", capture=True).stdout.splitlines()
            )

    def test_subp_update_env(self):
        """test that subp's update_env argument updates the environment"""
        extra = {"FOO": "BAR", "HOME": "/root", "K1": "V1"}
        with mock.patch.dict("os.environ", values=extra):
            out, _err = subp.subp(
                "env",
                capture=True,
                update_env={"HOME": "/myhome", "K2": "V2"},
            )

        assert {"FOO=BAR", "HOME=/myhome", "K1=V1", "K2=V2"}.issubset(
            set(out.splitlines())
        )

    def test_subp_warn_missing_shebang(self, tmp_path):
        """Warn on no #! in script"""
        noshebang = str(tmp_path / "noshebang")
        util.write_file(noshebang, "true\n")

        print("os is %s" % os)
        os.chmod(noshebang, os.stat(noshebang).st_mode | stat.S_IEXEC)
        with pytest.raises(
            subp.ProcessExecutionError, match=r"Missing #! in script\?"
        ):
            subp.subp(
                (noshebang,),
            )

    def test_returns_none_if_no_capture(self):
        (out, err) = subp.subp(self.stdin2out, data=b"", capture=False)
        assert err is None
        assert out is None

    def test_exception_has_out_err_are_bytes_if_decode_false(self):
        """Raised exc should have stderr, stdout as bytes if no decode."""
        with pytest.raises(subp.ProcessExecutionError) as exc_info:
            subp.subp([BOGUS_COMMAND], decode=False)
        assert isinstance(exc_info.value.stdout, bytes)
        assert isinstance(exc_info.value.stderr, bytes)

    def test_exception_has_out_err_are_bytes_if_decode_true(self):
        """Raised exc should have stderr, stdout as string if no decode."""
        with pytest.raises(subp.ProcessExecutionError) as exc_info:
            subp.subp([BOGUS_COMMAND], decode=True)
        assert isinstance(exc_info.value.stdout, str)
        assert isinstance(exc_info.value.stderr, str)

    def test_exception_invalid_command(self):
        args = [None, "first", "arg", "missing"]
        with pytest.raises(subp.ProcessExecutionError):
            subp.subp(args)

    def test_bunch_of_slashes_in_path(self):
        assert "/target/my/path/" == subp.target_path("/target/", "//my/path/")
        assert "/target/my/path/" == subp.target_path(
            "/target/", "///my/path/"
        )

    def test_c_lang_can_take_utf8_args(self):
        """Independent of system LC_CTYPE, args can contain utf-8 strings.

        When python starts up, its default encoding gets set based on
        the value of LC_CTYPE.  If no system locale is set, the default
        encoding for both python2 and python3 in some paths will end up
        being ascii.

        Attempts to use setlocale or patching (or changing) os.environ
        in the current environment seem to not be effective.

        This test starts up a python with LC_CTYPE set to C so that
        the default encoding will be set to ascii.  In such an environment
        Popen(['command', 'non-ascii-arg']) would cause a UnicodeDecodeError.
        """
        python_prog = "\n".join(
            [
                "import json, sys",
                'sys.path.insert(0, "{}")'.format(get_top_level_dir()),
                "from cloudinit.subp import subp",
                "data = sys.stdin.read()",
                "cmd = json.loads(data)",
                "subp(cmd, capture=False)",
                "",
            ]
        )
        cmd = [
            SH,
            "-c",
            'printf "$@"',
            "--",
            self.utf8_valid.decode("utf-8"),
        ]
        python_subp = [sys.executable, "-c", python_prog]

        out, _err = subp.subp(
            python_subp,
            update_env={"LC_CTYPE": "C"},
            data=json.dumps(cmd).encode("utf-8"),
            decode=False,
        )
        assert self.utf8_valid == out
