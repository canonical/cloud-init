# This file is part of cloud-init. See LICENSE file for license information.
"""Common utility functions for interacting with subprocess."""

import collections
import logging
import os
import subprocess
import time
from errno import ENOEXEC
from io import TextIOWrapper
from typing import List, Optional, Union

LOG = logging.getLogger(__name__)

SubpResult = collections.namedtuple("SubpResult", ["stdout", "stderr"])


def prepend_base_command(base_command, commands):
    """Ensure user-provided commands start with base_command; warn otherwise.

    Each command is either a list or string. Perform the following:
       - If the command is a list, pop the first element if it is None
       - If the command is a list, insert base_command as the first element if
         not present.
       - When the command is a string not starting with 'base-command', warn.

    Allow flexibility to provide non-base-command environment/config setup if
    needed.

    @commands: List of commands. Each command element is a list or string.

    @return: List of 'fixed up' commands.
    @raise: TypeError on invalid config item type.
    """
    warnings = []
    errors = []
    fixed_commands = []
    for command in commands:
        if isinstance(command, list):
            if command[0] is None:  # Avoid warnings by specifying None
                command = command[1:]
            elif command[0] != base_command:  # Automatically prepend
                command.insert(0, base_command)
        elif isinstance(command, str):
            if not command.startswith(f"{base_command} "):
                warnings.append(command)
        else:
            errors.append(str(command))
            continue
        fixed_commands.append(command)

    if warnings:
        LOG.warning(
            "Non-%s commands in %s config:\n%s",
            base_command,
            base_command,
            "\n".join(warnings),
        )
    if errors:
        raise TypeError(
            "Invalid {name} config."
            " These commands are not a string or list:\n{errors}".format(
                name=base_command, errors="\n".join(errors)
            )
        )
    return fixed_commands


class ProcessExecutionError(IOError):
    MESSAGE_TMPL = (
        "%(description)s\n"
        "Command: %(cmd)s\n"
        "Exit code: %(exit_code)s\n"
        "Reason: %(reason)s\n"
        "Stdout: %(stdout)s\n"
        "Stderr: %(stderr)s"
    )
    empty_attr = "-"

    def __init__(
        self,
        stdout=None,
        stderr=None,
        exit_code=None,
        cmd=None,
        description=None,
        reason=None,
        errno=None,
    ):
        self.cmd = cmd or self.empty_attr

        if description:
            self.description = description
        elif not exit_code and errno == ENOEXEC:
            self.description = "Exec format error. Missing #! in script?"
        else:
            self.description = "Unexpected error while running command."

        self.exit_code = (
            exit_code if isinstance(exit_code, int) else self.empty_attr
        )

        if not stderr:
            self.stderr = self.empty_attr if stderr is None else stderr
        else:
            self.stderr = self._indent_text(stderr)

        if not stdout:
            self.stdout = self.empty_attr if stdout is None else stdout
        else:
            self.stdout = self._indent_text(stdout)

        self.reason = reason or self.empty_attr

        if errno:
            self.errno = errno
        message = self.MESSAGE_TMPL % {
            "description": self._ensure_string(self.description),
            "cmd": self._ensure_string(self.cmd),
            "exit_code": self._ensure_string(self.exit_code),
            "stdout": self._ensure_string(self.stdout),
            "stderr": self._ensure_string(self.stderr),
            "reason": self._ensure_string(self.reason),
        }
        IOError.__init__(self, message)

    def _ensure_string(self, text):
        """
        if data is bytes object, decode
        """
        return text.decode() if isinstance(text, bytes) else text

    def _indent_text(
        self, text: Union[str, bytes], indent_level=8
    ) -> Union[str, bytes]:
        """
        indent text on all but the first line, allowing for easy to read output

        remove any newlines at end of text first to prevent unneeded blank
        line in output
        """
        if not isinstance(text, bytes):
            return text.rstrip("\n").replace("\n", "\n" + " " * indent_level)
        return text.rstrip(b"\n").replace(b"\n", b"\n" + b" " * indent_level)


def raise_on_invalid_command(args: Union[List[str], List[bytes]]):
    """check argument types to ensure that subp() can run the argument

    Throw a user-friendly exception which explains the issue.

    args: list of arguments passed to subp()
    raises: ProcessExecutionError with information explaining the issue
    """
    for component in args:
        # if already bytes, or implements encode(), then it should be safe
        if not (isinstance(component, bytes) or hasattr(component, "encode")):
            LOG.warning("Running invalid command: %s", args)
            raise ProcessExecutionError(
                cmd=args, reason=f"Running invalid command: {args}"
            )


def subp(
    args: Union[str, bytes, List[str], List[bytes]],
    *,
    data=None,
    rcs=None,
    capture=True,
    shell=False,
    logstring=False,
    decode="replace",
    update_env=None,
    cwd=None,
    timeout=None,
) -> SubpResult:
    """Run a subprocess.

    :param args: command to run in a list. [cmd, arg1, arg2...]
    :param data: input to the command, made available on its stdin.
    :param rcs:
        a list of allowed return codes.  If subprocess exits with a value not
        in this list, a ProcessExecutionError will be raised.  By default,
        data is returned as a string.  See 'decode' parameter.
    :param capture:
        boolean indicating if output should be captured.  If True, then stderr
        and stdout will be returned.  If False, they will not be redirected.
    :param shell: boolean indicating if this should be run with a shell.
    :param logstring:
        the command will be logged to DEBUG.  If it contains info that should
        not be logged, then logstring will be logged instead.
    :param decode:
        if False, no decoding will be done and returned stdout and stderr will
        be bytes.  Other allowed values are 'strict', 'ignore', and 'replace'.
        These values are passed through to bytes().decode() as the 'errors'
        parameter.  There is no support for decoding to other than utf-8.
    :param update_env:
        update the environment for this command with this dictionary.
        this will not affect the current processes os.environ.
    :param cwd:
        change the working directory to cwd before executing the command.
    :param timeout: maximum time for the subprocess to run, passed directly to
        the timeout parameter of Popen.communicate()

    :return
        if not capturing, return is (None, None)
        if capturing, stdout and stderr are returned.
            if decode:
                entries in tuple will be string
            if not decode:
                entries in tuple will be bytes
    """

    if rcs is None:
        rcs = [0]

    env = os.environ.copy()
    if update_env:
        env.update(update_env)

    LOG.debug(
        "Running command %s with allowed return codes %s"
        " (shell=%s, capture=%s)",
        logstring if logstring else args,
        rcs,
        shell,
        capture,
    )

    stdin: Union[TextIOWrapper, int]
    stdout = None
    stderr = None
    if capture:
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE
    if data is None:
        # using devnull assures any reads get null, rather
        # than possibly waiting on input.
        stdin = subprocess.DEVNULL
    else:
        stdin = subprocess.PIPE
        if not isinstance(data, bytes):
            data = data.encode()

    # Popen converts entries in the arguments array from non-bytes to bytes.
    # When locale is unset it may use ascii for that encoding which can
    # cause UnicodeDecodeErrors. (LP: #1751051)
    bytes_args: Union[bytes, List[bytes]]
    if isinstance(args, bytes):
        bytes_args = args
    elif isinstance(args, str):
        bytes_args = args.encode("utf-8")
    else:
        raise_on_invalid_command(args)
        bytes_args = [
            x if isinstance(x, bytes) else x.encode("utf-8") for x in args
        ]
    try:
        before = time.monotonic()
        sp = subprocess.Popen(
            bytes_args,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            env=env,
            shell=shell,
            cwd=cwd,
        )
        out, err = sp.communicate(data, timeout=timeout)
        total = time.monotonic() - before
        if total > 0.1:
            LOG.debug(
                "%s took %.3ss to run",
                logstring if logstring else args,
                total,
            )
    except OSError as e:
        raise ProcessExecutionError(
            cmd=args,
            reason=e,
            errno=e.errno,
            stdout="-" if decode else b"-",
            stderr="-" if decode else b"-",
        ) from e
    if decode:

        def ldecode(data, m="utf-8"):
            return data.decode(m, decode) if isinstance(data, bytes) else data

        out = ldecode(out)
        err = ldecode(err)

    rc = sp.returncode
    if rc not in rcs:
        raise ProcessExecutionError(
            stdout=out, stderr=err, exit_code=rc, cmd=args
        )
    return SubpResult(out, err)


def target_path(target=None, path=None):
    # return 'path' inside target, accepting target as None
    if target in (None, ""):
        target = "/"
    elif not isinstance(target, str):
        raise ValueError(f"Unexpected input for target: {target}")
    else:
        target = os.path.abspath(target)
        # abspath("//") returns "//" specifically for 2 slashes.
        if target.startswith("//"):
            target = target[1:]

    if not path:
        return target

    # os.path.join("/etc", "/foo") returns "/foo". Chomp all leading /.
    while len(path) and path[0] == "/":
        path = path[1:]
    return os.path.join(target, path)


def which(program, search=None, target=None) -> Optional[str]:
    target = target_path(target)

    if os.path.sep in program and is_exe(target_path(target, program)):
        # if program had a '/' in it, then do not search PATH
        # 'which' does consider cwd here. (cd / && which bin/ls) = bin/ls
        # so effectively we set cwd to / (or target)
        return program

    if search is None:
        paths = [
            p.strip('"') for p in os.environ.get("PATH", "").split(os.pathsep)
        ]
        search = (
            paths if target == "/" else [p for p in paths if p.startswith("/")]
        )
    # normalize path input
    search = [os.path.abspath(p) for p in search]

    for path in search:
        ppath = os.path.sep.join((path, program))
        if is_exe(target_path(target, ppath)):
            return ppath

    return None


def is_exe(fpath):
    # return boolean indicating if fpath exists and is executable.
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def runparts(dirp, skip_no_exist=True, exe_prefix=None):
    if skip_no_exist and not os.path.isdir(dirp):
        return

    failed = []
    attempted = []

    if exe_prefix is None:
        prefix = []
    elif isinstance(exe_prefix, str):
        prefix = [str(exe_prefix)]
    elif isinstance(exe_prefix, list):
        prefix = exe_prefix
    else:
        raise TypeError("exe_prefix must be None, str, or list")

    for exe_name in sorted(os.listdir(dirp)):
        exe_path = os.path.join(dirp, exe_name)
        if is_exe(exe_path):
            attempted.append(exe_path)
            try:
                subp(prefix + [exe_path], capture=False)
            except ProcessExecutionError as e:
                LOG.debug(e)
                failed.append(exe_name)
        elif os.path.isfile(exe_path):
            LOG.warning(
                "skipping %s as its not executable "
                "or the underlying file system is mounted without "
                "executable permissions.",
                exe_path,
            )
        else:
            LOG.debug("Not executing special file [%s]", exe_path)

    if failed and attempted:
        raise RuntimeError(
            f'Runparts: {len(failed)} failures ({",".join(failed)}) in '
            f"{len(attempted)} attempted commands"
        )
