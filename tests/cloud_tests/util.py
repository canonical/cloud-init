# This file is part of cloud-init. See LICENSE file for license information.

"""Utilities for re-use across integration tests."""

import base64
import copy
import glob
import os
import random
import shlex
import shutil
import string
import subprocess
import tempfile
import yaml

from cloudinit import util as c_util
from tests.cloud_tests import LOG

OS_FAMILY_MAPPING = {
    'debian': ['debian', 'ubuntu'],
    'redhat': ['centos', 'rhel', 'fedora'],
    'gentoo': ['gentoo'],
    'freebsd': ['freebsd'],
    'suse': ['sles'],
    'arch': ['arch'],
}


def list_test_data(data_dir):
    """Find all tests with test data available in data_dir.

    @param data_dir: should contain <platforms>/<os_name>/<testnames>/<data>
    @return_value: {<platform>: {<os_name>: [<testname>]}}
    """
    if not os.path.isdir(data_dir):
        raise ValueError("bad data dir")

    res = {}
    for platform in os.listdir(data_dir):
        if not os.path.isdir(os.path.join(data_dir, platform)):
            continue

        res[platform] = {}
        for os_name in os.listdir(os.path.join(data_dir, platform)):
            res[platform][os_name] = [
                os.path.sep.join(f.split(os.path.sep)[-2:]) for f in
                glob.glob(os.sep.join((data_dir, platform, os_name, '*/*')))]

    LOG.debug('found test data: %s\n', res)
    return res


def gen_instance_name(prefix='cloud-test', image_desc=None, use_desc=None,
                      max_len=63, delim='-', max_tries=16, used_list=None,
                      valid=string.ascii_lowercase + string.digits):
    """Generate an unique name for a test instance.

    @param prefix: name prefix, defaults to cloud-test, default should be left
    @param image_desc: short string (len <= 16) with image desc
    @param use_desc: short string (len <= 30) with usage desc
    @param max_len: maximum name length, defaults to 64 chars
    @param delim: delimiter to use between tokens
    @param max_tries: maximum tries to find a unique name before giving up
    @param used_list: already used names, or none to not check
    @param valid: string of valid characters for name
    @return_value: valid, unused name, may raise StopIteration
    """
    unknown = 'unknown'

    def join(*args):
        """Join args with delim."""
        return delim.join(args)

    def fill(*args):
        """Join name elems and fill rest with random data."""
        name = join(*args)
        num = max_len - len(name) - len(delim)
        return join(name, ''.join(random.choice(valid) for _ in range(num)))

    def clean(elem, max_len):
        """Filter bad characters out of elem and trim to length."""
        elem = elem.lower()[:max_len] if elem else unknown
        return ''.join(c if c in valid else delim for c in elem)

    return next(name for name in
                (fill(prefix, clean(image_desc, 16), clean(use_desc, 30))
                 for _ in range(max_tries))
                if not used_list or name not in used_list)


def sorted_unique(iterable, key=None, reverse=False):
    """Create unique sorted list.

    @param iterable: the data structure to sort
    @param key: if you have a specific key
    @param reverse: to reverse or not
    @return_value: a sorted list of unique items in iterable
    """
    return sorted(set(iterable), key=key, reverse=reverse)


def get_os_family(os_name):
    """Get os family type for os_name.

    @param os_name: name of os
    @return_value: family name for os_name
    """
    return next((k for k, v in OS_FAMILY_MAPPING.items()
                 if os_name.lower() in v), None)


def current_verbosity():
    """Get verbosity currently in effect from log level.

    @return_value: verbosity, 0-2, 2=verbose, 0=quiet
    """
    return max(min(3 - int(LOG.level / 10), 2), 0)


def is_writable_dir(path):
    """Make sure dir is writable.

    @param path: path to determine if writable
    @return_value: boolean with result
    """
    try:
        c_util.ensure_dir(path)
        os.remove(tempfile.mkstemp(dir=os.path.abspath(path))[1])
    except (IOError, OSError):
        return False
    return True


def is_clean_writable_dir(path):
    """Make sure dir is empty and writable, creating it if it does not exist.

    @param path: path to check
    @return_value: True/False if successful
    """
    path = os.path.abspath(path)
    if not (is_writable_dir(path) and len(os.listdir(path)) == 0):
        return False
    return True


def configure_yaml():
    """Clean yaml."""
    yaml.add_representer(str, (lambda dumper, data: dumper.represent_scalar(
        'tag:yaml.org,2002:str', data, style='|' if '\n' in data else '')))


def yaml_format(data, content_type=None):
    """Format data as yaml.

    @param data: data to dump
    @param header: if specified, add a header to the dumped data
    @return_value: yaml string
    """
    configure_yaml()
    content_type = (
        '#{}\n'.format(content_type.strip('#\n')) if content_type else '')
    return content_type + yaml.dump(data, indent=2, default_flow_style=False)


def yaml_dump(data, path):
    """Dump data to path in yaml format."""
    c_util.write_file(os.path.abspath(path), yaml_format(data), omode='w')


def merge_results(data, path):
    """Handle merging results from collect phase and verify phase."""
    current = {}
    if os.path.exists(path):
        with open(path, 'r') as fp:
            current = c_util.load_yaml(fp.read())
    current.update(data)
    yaml_dump(current, path)


def rel_files(basedir):
    """List of files under directory by relative path, not including dirs.

    @param basedir: directory to search
    @return_value: list or relative paths
    """
    basedir = os.path.normpath(basedir)
    return [path[len(basedir) + 1:] for path in
            glob.glob(os.path.join(basedir, '**'), recursive=True)
            if not os.path.isdir(path)]


def flat_tar(output, basedir, owner='root', group='root'):
    """Create a flat tar archive (no leading ./) from basedir.

    @param output: output tar file to write
    @param basedir: base directory for archive
    @param owner: owner of archive files
    @param group: group archive files belong to
    @return_value: none
    """
    c_util.subp(['tar', 'cf', output, '--owner', owner, '--group', group,
                 '-C', basedir] + rel_files(basedir), capture=True)


def parse_conf_list(entries, valid=None, boolean=False):
    """Parse config in a list of strings in key=value format.

    @param entries: list of key=value strings
    @param valid: list of valid keys in result, return None if invalid input
    @param boolean: if true, then interpret all values as booleans
    @return_value: dict of configuration or None if invalid
    """
    res = {key: value.lower() == 'true' if boolean else value
           for key, value in (i.split('=') for i in entries)}
    return res if not valid or all(k in valid for k in res.keys()) else None


def update_args(args, updates, preserve_old=True):
    """Update cmdline arguments from a dictionary.

    @param args: cmdline arguments
    @param updates: dictionary of {arg_name: new_value} mappings
    @param preserve_old: if true, create a deep copy of args before updating
    @return_value: updated cmdline arguments
    """
    args = copy.deepcopy(args) if preserve_old else args
    if updates:
        vars(args).update(updates)
    return args


def update_user_data(user_data, updates, dump_to_yaml=True):
    """Update user_data from dictionary.

    @param user_data: user data as yaml string or dict
    @param updates: dictionary to merge with user data
    @param dump_to_yaml: return as yaml dumped string if true
    @return_value: updated user data, as yaml string if dump_to_yaml is true
    """
    user_data = (c_util.load_yaml(user_data)
                 if isinstance(user_data, str) else copy.deepcopy(user_data))
    user_data.update(updates)
    return (yaml_format(user_data, content_type='cloud-config')
            if dump_to_yaml else user_data)


def shell_safe(cmd):
    """Produce string safe shell string.

    Create a string that can be passed to:
         set -- <string>
    to produce the same array that cmd represents.

    Internally we utilize 'getopt's ability/knowledge on how to quote
    strings to be safe for shell.  This implementation could be changed
    to be pure python.  It is just a matter of correctly escaping
    or quoting characters like: ' " ^ & $ ; ( ) ...

    @param cmd: command as a list
    """
    out = subprocess.check_output(
        ["getopt", "--shell", "sh", "--options", "", "--", "--"] + list(cmd))
    # out contains ' -- <data>\n'. drop the ' -- ' and the '\n'
    return out.decode()[4:-1]


def shell_pack(cmd):
    """Return a string that can shuffled through 'sh' and execute cmd.

    In Python subprocess terms:
        check_output(cmd) == check_output(shell_pack(cmd), shell=True)

    @param cmd: list or string of command to pack up
    """

    if isinstance(cmd, str):
        cmd = [cmd]
    else:
        cmd = list(cmd)

    stuffed = shell_safe(cmd)
    # for whatever reason b64encode returns bytes when it is clearly
    # representable as a string by nature of being base64 encoded.
    b64 = base64.b64encode(stuffed.encode()).decode()
    return 'eval set -- "$(echo %s | base64 --decode)" && exec "$@"' % b64


def shell_quote(cmd):
    if isinstance(cmd, (tuple, list)):
        return ' '.join([shlex.quote(x) for x in cmd])
    return shlex.quote(cmd)


class TargetBase(object):
    _tmp_count = 0

    def execute(self, command, stdin=None, env=None,
                rcs=None, description=None):
        """Execute command in instance, recording output, error and exit code.

        Assumes functional networking and execution as root with the
        target filesystem being available at /.

        @param command: the command to execute as root inside the image
            if command is a string, then it will be executed as:
            ['sh', '-c', command]
        @param stdin: bytes content for standard in
        @param env: environment variables
        @param rcs: return codes.
                    None (default): non-zero exit code will raise exception.
                    False: any is allowed (No execption raised).
                    list of int: any rc not in the list will raise exception.
        @param description: purpose of command
        @return_value: tuple containing stdout data, stderr data, exit code
        """
        if isinstance(command, str):
            command = ['sh', '-c', command]

        if rcs is None:
            rcs = (0,)

        if description:
            LOG.debug('executing "%s"', description)
        else:
            LOG.debug("executing command: %s", shell_quote(command))

        out, err, rc = self._execute(command=command, stdin=stdin, env=env)

        # False means accept anything.
        if (rcs is False or rc in rcs):
            return out, err, rc

        raise InTargetExecuteError(out, err, rc, command, description)

    def _execute(self, command, stdin=None, env=None):
        """Execute command in inside, return stdout, stderr and exit code.

        Assumes functional networking and execution as root with the
        target filesystem being available at /.

        @param stdin: bytes content for standard in
        @param env: environment variables
        @return_value: tuple containing stdout data, stderr data, exit code

        This is intended to be implemented by the Image or Instance.
        Many callers will use the higher level 'execute'."""
        raise NotImplementedError("_execute must be implemented by subclass.")

    def read_data(self, remote_path, decode=False):
        """Read data from instance filesystem.

        @param remote_path: path in instance
        @param decode: decode data before returning.
        @return_value: content of remote_path as bytes if 'decode' is False,
                       and as string if 'decode' is True.
        """
        # when sh is invoked with '-c', then the first argument is "$0"
        # which is commonly understood as the "program name".
        # 'read_data' is the program name, and 'remote_path' is '$1'
        stdout, _stderr, rc = self._execute(
            ["sh", "-c", 'exec cat "$1"', 'read_data', remote_path])
        if rc != 0:
            raise RuntimeError("Failed to read file '%s'" % remote_path)

        if decode:
            return stdout.decode()
        return stdout

    def write_data(self, remote_path, data):
        """Write data to instance filesystem.

        @param remote_path: path in instance
        @param data: data to write in bytes
        """
        # when sh is invoked with '-c', then the first argument is "$0"
        # which is commonly understood as the "program name".
        # 'write_data' is the program name, and 'remote_path' is '$1'
        _, _, rc = self._execute(
            ["sh", "-c", 'exec cat >"$1"', 'write_data', remote_path],
            stdin=data)

        if rc != 0:
            raise RuntimeError("Failed to write to '%s'" % remote_path)
        return

    def pull_file(self, remote_path, local_path):
        """Copy file at 'remote_path', from instance to 'local_path'.

        @param remote_path: path on remote instance
        @param local_path: path on local instance
        """
        with open(local_path, 'wb') as fp:
            fp.write(self.read_data(remote_path))

    def push_file(self, local_path, remote_path):
        """Copy file at 'local_path' to instance at 'remote_path'.

        @param local_path: path on local instance
        @param remote_path: path on remote instance"""
        with open(local_path, "rb") as fp:
            self.write_data(remote_path, data=fp.read())

    def run_script(self, script, rcs=None, description=None):
        """Run script in target and return stdout.

        @param script: script contents
        @param rcs: allowed return codes from script
        @param description: purpose of script
        @return_value: stdout from script
        """
        # Just write to a file, add execute, run it, then remove it.
        shblob = '; '.join((
            'set -e',
            's="$1"',
            'shift',
            'cat > "$s"',
            'trap "rm -f $s" EXIT',
            'chmod +x "$s"',
            '"$s" "$@"'))
        return self.execute(
            ['sh', '-c', shblob, 'runscript', self.tmpfile()],
            stdin=script, description=description, rcs=rcs)

    def tmpfile(self):
        """Get a tmp file in the target.

        @return_value: path to new file in target
        """
        path = "/tmp/%s-%04d" % (type(self).__name__, self._tmp_count)
        self._tmp_count += 1
        return path


class InTargetExecuteError(c_util.ProcessExecutionError):
    """Error type for in target commands that fail."""

    default_desc = 'Unexpected error while running command.'

    def __init__(self, stdout, stderr, exit_code, cmd, description=None,
                 reason=None):
        """Init error and parent error class."""
        super(InTargetExecuteError, self).__init__(
            stdout=stdout, stderr=stderr, exit_code=exit_code,
            cmd=shell_quote(cmd),
            description=description if description else self.default_desc,
            reason=reason)


class PlatformError(IOError):
    """Error type for platform errors."""

    default_desc = 'unexpected error in platform.'

    def __init__(self, operation, description=None):
        """Init error and parent error class."""
        description = description if description else self.default_desc

        message = '%s: %s' % (operation, description)
        IOError.__init__(self, message)


def mkdtemp(prefix='cloud_test_data'):
    return tempfile.mkdtemp(prefix=prefix)


class TempDir(object):
    """Configurable temporary directory like tempfile.TemporaryDirectory."""

    def __init__(self, tmpdir=None, preserve=False, prefix='cloud_test_data_'):
        """Initialize.

        @param tmpdir: directory to use as tempdir
        @param preserve: if true, always preserve data on exit
        @param prefix: prefix to use for tempfile name
        """
        self.tmpdir = tmpdir
        self.preserve = preserve
        self.prefix = prefix

    def __enter__(self):
        """Create tempdir.

        @return_value: tempdir path
        """
        if not self.tmpdir:
            self.tmpdir = mkdtemp(prefix=self.prefix)
        LOG.debug('using tmpdir: %s', self.tmpdir)
        return self.tmpdir

    def __exit__(self, etype, value, trace):
        """Destroy tempdir if no errors occurred."""
        if etype or self.preserve:
            LOG.info('leaving data in %s', self.tmpdir)
        else:
            shutil.rmtree(self.tmpdir)

# vi: ts=4 expandtab
