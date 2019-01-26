# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'collect-logs' utility and handler to include in cloud-init cmd."""

import argparse
from datetime import datetime
import os
import shutil
import sys

from cloudinit.sources import INSTANCE_JSON_SENSITIVE_FILE
from cloudinit.temp_utils import tempdir
from cloudinit.util import (
    ProcessExecutionError, chdir, copy, ensure_dir, subp, write_file)


CLOUDINIT_LOGS = ['/var/log/cloud-init.log', '/var/log/cloud-init-output.log']
CLOUDINIT_RUN_DIR = '/run/cloud-init'
USER_DATA_FILE = '/var/lib/cloud/instance/user-data.txt'  # Optional


def get_parser(parser=None):
    """Build or extend and arg parser for collect-logs utility.

    @param parser: Optional existing ArgumentParser instance representing the
        collect-logs subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog='collect-logs',
            description='Collect and tar all cloud-init debug info')
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        dest='verbosity', help="Be more verbose.")
    parser.add_argument(
        "--tarfile", '-t', default='cloud-init.tar.gz',
        help=('The tarfile to create containing all collected logs.'
              ' Default: cloud-init.tar.gz'))
    parser.add_argument(
        "--include-userdata", '-u', default=False, action='store_true',
        dest='userdata', help=(
            'Optionally include user-data from {0} which could contain'
            ' sensitive information.'.format(USER_DATA_FILE)))
    return parser


def _copytree_ignore_sensitive_files(curdir, files):
    """Return a list of files to ignore if we are non-root"""
    if os.getuid() == 0:
        return ()
    return (INSTANCE_JSON_SENSITIVE_FILE,)  # Ignore root-permissioned files


def _write_command_output_to_file(cmd, filename, msg, verbosity):
    """Helper which runs a command and writes output or error to filename."""
    try:
        out, _ = subp(cmd)
    except ProcessExecutionError as e:
        write_file(filename, str(e))
        _debug("collecting %s failed.\n" % msg, 1, verbosity)
    else:
        write_file(filename, out)
        _debug("collected %s\n" % msg, 1, verbosity)
        return out


def _debug(msg, level, verbosity):
    if level <= verbosity:
        sys.stderr.write(msg)


def _collect_file(path, out_dir, verbosity):
    if os.path.isfile(path):
        copy(path, out_dir)
        _debug("collected file: %s\n" % path, 1, verbosity)
    else:
        _debug("file %s did not exist\n" % path, 2, verbosity)


def collect_logs(tarfile, include_userdata, verbosity=0):
    """Collect all cloud-init logs and tar them up into the provided tarfile.

    @param tarfile: The path of the tar-gzipped file to create.
    @param include_userdata: Boolean, true means include user-data.
    """
    if include_userdata and os.getuid() != 0:
        sys.stderr.write(
            "To include userdata, root user is required."
            " Try sudo cloud-init collect-logs\n")
        return 1
    tarfile = os.path.abspath(tarfile)
    date = datetime.utcnow().date().strftime('%Y-%m-%d')
    log_dir = 'cloud-init-logs-{0}'.format(date)
    with tempdir(dir='/tmp') as tmp_dir:
        log_dir = os.path.join(tmp_dir, log_dir)
        version = _write_command_output_to_file(
            ['cloud-init', '--version'],
            os.path.join(log_dir, 'version'),
            "cloud-init --version", verbosity)
        dpkg_ver = _write_command_output_to_file(
            ['dpkg-query', '--show', "-f=${Version}\n", 'cloud-init'],
            os.path.join(log_dir, 'dpkg-version'),
            "dpkg version", verbosity)
        if not version:
            version = dpkg_ver if dpkg_ver else "not-available"
        _debug("collected cloud-init version: %s\n" % version, 1, verbosity)
        _write_command_output_to_file(
            ['dmesg'], os.path.join(log_dir, 'dmesg.txt'),
            "dmesg output", verbosity)
        _write_command_output_to_file(
            ['journalctl', '--boot=0', '-o', 'short-precise'],
            os.path.join(log_dir, 'journal.txt'),
            "systemd journal of current boot", verbosity)

        for log in CLOUDINIT_LOGS:
            _collect_file(log, log_dir, verbosity)
        if include_userdata:
            _collect_file(USER_DATA_FILE, log_dir, verbosity)
        run_dir = os.path.join(log_dir, 'run')
        ensure_dir(run_dir)
        if os.path.exists(CLOUDINIT_RUN_DIR):
            shutil.copytree(CLOUDINIT_RUN_DIR,
                            os.path.join(run_dir, 'cloud-init'),
                            ignore=_copytree_ignore_sensitive_files)
            _debug("collected dir %s\n" % CLOUDINIT_RUN_DIR, 1, verbosity)
        else:
            _debug("directory '%s' did not exist\n" % CLOUDINIT_RUN_DIR, 1,
                   verbosity)
        with chdir(tmp_dir):
            subp(['tar', 'czvf', tarfile, log_dir.replace(tmp_dir + '/', '')])
    sys.stderr.write("Wrote %s\n" % tarfile)
    return 0


def handle_collect_logs_args(name, args):
    """Handle calls to 'cloud-init collect-logs' as a subcommand."""
    return collect_logs(args.tarfile, args.userdata, args.verbosity)


def main():
    """Tool to collect and tar all cloud-init related logs."""
    parser = get_parser()
    return handle_collect_logs_args('collect-logs', parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())

# vi: ts=4 expandtab
