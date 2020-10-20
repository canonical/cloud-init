# This file is part of cloud-init. See LICENSE file for license information.
"""Common utility functions for interacting with subprocess."""

import logging
import os
import subprocess

from errno import ENOEXEC

LOG = logging.getLogger(__name__)


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
            if not command.startswith('%s ' % base_command):
                warnings.append(command)
        else:
            errors.append(str(command))
            continue
        fixed_commands.append(command)

    if warnings:
        LOG.warning(
            'Non-%s commands in %s config:\n%s',
            base_command, base_command, '\n'.join(warnings))
    if errors:
        raise TypeError(
            'Invalid {name} config.'
            ' These commands are not a string or list:\n{errors}'.format(
                name=base_command, errors='\n'.join(errors)))
    return fixed_commands


class ProcessExecutionError(IOError):

    MESSAGE_TMPL = ('%(description)s\n'
                    'Command: %(cmd)s\n'
                    'Exit code: %(exit_code)s\n'
                    'Reason: %(reason)s\n'
                    'Stdout: %(stdout)s\n'
                    'Stderr: %(stderr)s')
    empty_attr = '-'

    def __init__(self, stdout=None, stderr=None,
                 exit_code=None, cmd=None,
                 description=None, reason=None,
                 errno=None):
        if not cmd:
            self.cmd = self.empty_attr
        else:
            self.cmd = cmd

        if not description:
            if not exit_code and errno == ENOEXEC:
                self.description = 'Exec format error. Missing #! in script?'
            else:
                self.description = 'Unexpected error while running command.'
        else:
            self.description = description

        if not isinstance(exit_code, int):
            self.exit_code = self.empty_attr
        else:
            self.exit_code = exit_code

        if not stderr:
            if stderr is None:
                self.stderr = self.empty_attr
            else:
                self.stderr = stderr
        else:
            self.stderr = self._indent_text(stderr)

        if not stdout:
            if stdout is None:
                self.stdout = self.empty_attr
            else:
                self.stdout = stdout
        else:
            self.stdout = self._indent_text(stdout)

        if reason:
            self.reason = reason
        else:
            self.reason = self.empty_attr

        self.errno = errno
        message = self.MESSAGE_TMPL % {
            'description': self._ensure_string(self.description),
            'cmd': self._ensure_string(self.cmd),
            'exit_code': self._ensure_string(self.exit_code),
            'stdout': self._ensure_string(self.stdout),
            'stderr': self._ensure_string(self.stderr),
            'reason': self._ensure_string(self.reason),
        }
        IOError.__init__(self, message)

    def _ensure_string(self, text):
        """
        if data is bytes object, decode
        """
        return text.decode() if isinstance(text, bytes) else text

    def _indent_text(self, text, indent_level=8):
        """
        indent text on all but the first line, allowing for easy to read output
        """
        cr = '\n'
        indent = ' ' * indent_level
        # if input is bytes, return bytes
        if isinstance(text, bytes):
            cr = cr.encode()
            indent = indent.encode()
        # remove any newlines at end of text first to prevent unneeded blank
        # line in output
        return text.rstrip(cr).replace(cr, cr + indent)


def subp(args, data=None, rcs=None, env=None, capture=True,
         combine_capture=False, shell=False,
         logstring=False, decode="replace", target=None, update_env=None,
         status_cb=None, cwd=None):
    """Run a subprocess.

    :param args: command to run in a list. [cmd, arg1, arg2...]
    :param data: input to the command, made available on its stdin.
    :param rcs:
        a list of allowed return codes.  If subprocess exits with a value not
        in this list, a ProcessExecutionError will be raised.  By default,
        data is returned as a string.  See 'decode' parameter.
    :param env: a dictionary for the command's environment.
    :param capture:
        boolean indicating if output should be captured.  If True, then stderr
        and stdout will be returned.  If False, they will not be redirected.
    :param combine_capture:
        boolean indicating if stderr should be redirected to stdout. When True,
        interleaved stderr and stdout will be returned as the first element of
        a tuple, the second will be empty string or bytes (per decode).
        if combine_capture is True, then output is captured independent of
        the value of capture.
    :param shell: boolean indicating if this should be run with a shell.
    :param logstring:
        the command will be logged to DEBUG.  If it contains info that should
        not be logged, then logstring will be logged instead.
    :param decode:
        if False, no decoding will be done and returned stdout and stderr will
        be bytes.  Other allowed values are 'strict', 'ignore', and 'replace'.
        These values are passed through to bytes().decode() as the 'errors'
        parameter.  There is no support for decoding to other than utf-8.
    :param target:
        not supported, kwarg present only to make function signature similar
        to curtin's subp.
    :param update_env:
        update the enviornment for this command with this dictionary.
        this will not affect the current processes os.environ.
    :param status_cb:
        call this fuction with a single string argument before starting
        and after finishing.
    :param cwd:
        change the working directory to cwd before executing the command.

    :return
        if not capturing, return is (None, None)
        if capturing, stdout and stderr are returned.
            if decode:
                entries in tuple will be python2 unicode or python3 string
            if not decode:
                entries in tuple will be python2 string or python3 bytes
    """

    # not supported in cloud-init (yet), for now kept in the call signature
    # to ease maintaining code shared between cloud-init and curtin
    if target is not None:
        raise ValueError("target arg not supported by cloud-init")

    if rcs is None:
        rcs = [0]

    devnull_fp = None

    if update_env:
        if env is None:
            env = os.environ
        env = env.copy()
        env.update(update_env)

    if target_path(target) != "/":
        args = ['chroot', target] + list(args)

    if status_cb:
        command = ' '.join(args) if isinstance(args, list) else args
        status_cb('Begin run command: {command}\n'.format(command=command))
    if not logstring:
        LOG.debug(("Running command %s with allowed return codes %s"
                   " (shell=%s, capture=%s)"),
                  args, rcs, shell, 'combine' if combine_capture else capture)
    else:
        LOG.debug(("Running hidden command to protect sensitive "
                   "input/output logstring: %s"), logstring)

    stdin = None
    stdout = None
    stderr = None
    if capture:
        stdout = subprocess.PIPE
        stderr = subprocess.PIPE
    if combine_capture:
        stdout = subprocess.PIPE
        stderr = subprocess.STDOUT
    if data is None:
        # using devnull assures any reads get null, rather
        # than possibly waiting on input.
        devnull_fp = open(os.devnull)
        stdin = devnull_fp
    else:
        stdin = subprocess.PIPE
        if not isinstance(data, bytes):
            data = data.encode()

    # Popen converts entries in the arguments array from non-bytes to bytes.
    # When locale is unset it may use ascii for that encoding which can
    # cause UnicodeDecodeErrors. (LP: #1751051)
    if isinstance(args, bytes):
        bytes_args = args
    elif isinstance(args, str):
        bytes_args = args.encode("utf-8")
    else:
        bytes_args = [
            x if isinstance(x, bytes) else x.encode("utf-8")
            for x in args]
    try:
        sp = subprocess.Popen(bytes_args, stdout=stdout,
                              stderr=stderr, stdin=stdin,
                              env=env, shell=shell, cwd=cwd)
        (out, err) = sp.communicate(data)
    except OSError as e:
        if status_cb:
            status_cb('ERROR: End run command: invalid command provided\n')
        raise ProcessExecutionError(
            cmd=args, reason=e, errno=e.errno,
            stdout="-" if decode else b"-",
            stderr="-" if decode else b"-"
        ) from e
    finally:
        if devnull_fp:
            devnull_fp.close()

    # Just ensure blank instead of none.
    if capture or combine_capture:
        if not out:
            out = b''
        if not err:
            err = b''
    if decode:
        def ldecode(data, m='utf-8'):
            if not isinstance(data, bytes):
                return data
            return data.decode(m, decode)

        out = ldecode(out)
        err = ldecode(err)

    rc = sp.returncode
    if rc not in rcs:
        if status_cb:
            status_cb(
                'ERROR: End run command: exit({code})\n'.format(code=rc))
        raise ProcessExecutionError(stdout=out, stderr=err,
                                    exit_code=rc,
                                    cmd=args)
    if status_cb:
        status_cb('End run command: exit({code})\n'.format(code=rc))
    return (out, err)


def target_path(target, path=None):
    # return 'path' inside target, accepting target as None
    if target in (None, ""):
        target = "/"
    elif not isinstance(target, str):
        raise ValueError("Unexpected input for target: %s" % target)
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


def which(program, search=None, target=None):
    target = target_path(target)

    if os.path.sep in program:
        # if program had a '/' in it, then do not search PATH
        # 'which' does consider cwd here. (cd / && which bin/ls) = bin/ls
        # so effectively we set cwd to / (or target)
        if is_exe(target_path(target, program)):
            return program

    if search is None:
        paths = [p.strip('"') for p in
                 os.environ.get("PATH", "").split(os.pathsep)]
        if target == "/":
            search = paths
        else:
            search = [p for p in paths if p.startswith("/")]

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

    if failed and attempted:
        raise RuntimeError(
            'Runparts: %s failures (%s) in %s attempted commands' %
            (len(failed), ",".join(failed), len(attempted)))


# vi: ts=4 expandtab
