# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.subp utility functions"""

import json
import os
import stat
import sys
from unittest import mock

from cloudinit import subp, util
from tests.unittests.helpers import CiTestCase, get_top_level_dir

BASH = subp.which("bash")
BOGUS_COMMAND = "this-is-not-expected-to-be-a-program-name"


class TestPrependBaseCommands(CiTestCase):
    with_logs = True

    def test_prepend_base_command_errors_on_neither_string_nor_list(self):
        """Raise an error for each command which is not a string or list."""
        orig_commands = ["ls", 1, {"not": "gonna work"}, ["basecmd", "list"]]
        with self.assertRaises(TypeError) as context_manager:
            subp.prepend_base_command(
                base_command="basecmd", commands=orig_commands
            )
        self.assertEqual(
            "Invalid basecmd config. These commands are not a string or"
            " list:\n1\n{'not': 'gonna work'}",
            str(context_manager.exception),
        )

    def test_prepend_base_command_warns_on_non_base_string_commands(self):
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
        self.assertEqual(
            "WARNING: Non-basecmd commands in basecmd config:\n"
            "ls\ntouch /blah\n",
            self.logs.getvalue(),
        )
        self.assertEqual(orig_commands, fixed_commands)

    def test_prepend_base_command_prepends_on_non_base_list_commands(self):
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
        self.assertEqual("", self.logs.getvalue())
        self.assertEqual(expected, fixed_commands)

    def test_prepend_base_command_removes_first_item_when_none(self):
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
        self.assertEqual("", self.logs.getvalue())
        self.assertEqual(expected, fixed_commands)


class TestSubp(CiTestCase):
    allowed_subp = [
        BASH,
        "cat",
        CiTestCase.SUBP_SHELL_TRUE,
        BOGUS_COMMAND,
        sys.executable,
    ]

    stdin2err = [BASH, "-c", "cat >&2"]
    stdin2out = ["cat"]
    utf8_invalid = b"ab\xaadef"
    utf8_valid = b"start \xc3\xa9 end"
    utf8_valid_2 = b"d\xc3\xa9j\xc8\xa7"
    printenv = [BASH, "-c", 'for n in "$@"; do echo "$n=${!n}"; done', "--"]

    def printf_cmd(self, *args):
        # bash's printf supports \xaa.  So does /usr/bin/printf
        # but by using bash, we remove dependency on another program.
        return [BASH, "-c", 'printf "$@"', "printf"] + list(args)

    def test_subp_handles_bytestrings(self):
        """subp can run a bytestring command if shell is True."""
        tmp_file = self.tmp_path("test.out")
        cmd = "echo HI MOM >> {tmp_file}".format(tmp_file=tmp_file)
        (out, _err) = subp.subp(cmd.encode("utf-8"), shell=True)
        self.assertEqual("", out)
        self.assertEqual("", _err)
        self.assertEqual("HI MOM\n", util.load_file(tmp_file))

    def test_subp_handles_strings(self):
        """subp can run a string command if shell is True."""
        tmp_file = self.tmp_path("test.out")
        cmd = "echo HI MOM >> {tmp_file}".format(tmp_file=tmp_file)
        (out, _err) = subp.subp(cmd, shell=True)
        self.assertEqual("", out)
        self.assertEqual("", _err)
        self.assertEqual("HI MOM\n", util.load_file(tmp_file))

    def test_subp_handles_utf8(self):
        # The given bytes contain utf-8 accented characters as seen in e.g.
        # the "deja dup" package in Ubuntu.
        cmd = self.printf_cmd(self.utf8_valid_2)
        (out, _err) = subp.subp(cmd, capture=True)
        self.assertEqual(out, self.utf8_valid_2.decode("utf-8"))

    def test_subp_respects_decode_false(self):
        (out, err) = subp.subp(
            self.stdin2out, capture=True, decode=False, data=self.utf8_valid
        )
        self.assertTrue(isinstance(out, bytes))
        self.assertTrue(isinstance(err, bytes))
        self.assertEqual(out, self.utf8_valid)

    def test_subp_decode_ignore(self):
        # this executes a string that writes invalid utf-8 to stdout
        (out, _err) = subp.subp(
            self.printf_cmd("abc\\xaadef"), capture=True, decode="ignore"
        )
        self.assertEqual(out, "abcdef")

    def test_subp_decode_strict_valid_utf8(self):
        (out, _err) = subp.subp(
            self.stdin2out, capture=True, decode="strict", data=self.utf8_valid
        )
        self.assertEqual(out, self.utf8_valid.decode("utf-8"))

    def test_subp_decode_invalid_utf8_replaces(self):
        (out, _err) = subp.subp(
            self.stdin2out, capture=True, data=self.utf8_invalid
        )
        expected = self.utf8_invalid.decode("utf-8", "replace")
        self.assertEqual(out, expected)

    def test_subp_decode_strict_raises(self):
        args = []
        kwargs = {
            "args": self.stdin2out,
            "capture": True,
            "decode": "strict",
            "data": self.utf8_invalid,
        }
        self.assertRaises(UnicodeDecodeError, subp.subp, *args, **kwargs)

    def test_subp_capture_stderr(self):
        data = b"hello world"
        (out, err) = subp.subp(
            self.stdin2err,
            capture=True,
            decode=False,
            data=data,
            update_env={"LC_ALL": "C"},
        )
        self.assertEqual(err, data)
        self.assertEqual(out, b"")

    def test_subp_reads_env(self):
        with mock.patch.dict("os.environ", values={"FOO": "BAR"}):
            out, _err = subp.subp(self.printenv + ["FOO"], capture=True)
        self.assertEqual("FOO=BAR", out.splitlines()[0])

    def test_subp_update_env(self):
        extra = {"FOO": "BAR", "HOME": "/root", "K1": "V1"}
        with mock.patch.dict("os.environ", values=extra):
            out, _err = subp.subp(
                self.printenv + ["FOO", "HOME", "K1", "K2"],
                capture=True,
                update_env={"HOME": "/myhome", "K2": "V2"},
            )

        self.assertEqual(
            ["FOO=BAR", "HOME=/myhome", "K1=V1", "K2=V2"], out.splitlines()
        )

    def test_subp_warn_missing_shebang(self):
        """Warn on no #! in script"""
        noshebang = self.tmp_path("noshebang")
        util.write_file(noshebang, "true\n")

        print("os is %s" % os)
        os.chmod(noshebang, os.stat(noshebang).st_mode | stat.S_IEXEC)
        with self.allow_subp([noshebang]):
            self.assertRaisesRegex(
                subp.ProcessExecutionError,
                r"Missing #! in script\?",
                subp.subp,
                (noshebang,),
            )

    def test_returns_none_if_no_capture(self):
        (out, err) = subp.subp(self.stdin2out, data=b"", capture=False)
        self.assertIsNone(err)
        self.assertIsNone(out)

    def test_exception_has_out_err_are_bytes_if_decode_false(self):
        """Raised exc should have stderr, stdout as bytes if no decode."""
        with self.assertRaises(subp.ProcessExecutionError) as cm:
            subp.subp([BOGUS_COMMAND], decode=False)
        self.assertTrue(isinstance(cm.exception.stdout, bytes))
        self.assertTrue(isinstance(cm.exception.stderr, bytes))

    def test_exception_has_out_err_are_bytes_if_decode_true(self):
        """Raised exc should have stderr, stdout as string if no decode."""
        with self.assertRaises(subp.ProcessExecutionError) as cm:
            subp.subp([BOGUS_COMMAND], decode=True)
        self.assertTrue(isinstance(cm.exception.stdout, str))
        self.assertTrue(isinstance(cm.exception.stderr, str))

    def test_bunch_of_slashes_in_path(self):
        self.assertEqual(
            "/target/my/path/", subp.target_path("/target/", "//my/path/")
        )
        self.assertEqual(
            "/target/my/path/", subp.target_path("/target/", "///my/path/")
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
            BASH,
            "-c",
            'echo -n "$@"',
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
        self.assertEqual(self.utf8_valid, out)
