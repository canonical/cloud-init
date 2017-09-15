# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'collect-logs' utility and handler to include in cloud-init cmd."""

import argparse
from cloudinit.util import (
    ProcessExecutionError, chdir, copy, ensure_dir, subp, write_file)
from cloudinit.temp_utils import tempdir
from datetime import datetime
import os
import shutil


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


def _write_command_output_to_file(cmd, filename):
    """Helper which runs a command and writes output or error to filename."""
    try:
        out, _ = subp(cmd)
    except ProcessExecutionError as e:
        write_file(filename, str(e))
    else:
        write_file(filename, out)


def collect_logs(tarfile, include_userdata):
    """Collect all cloud-init logs and tar them up into the provided tarfile.

    @param tarfile: The path of the tar-gzipped file to create.
    @param include_userdata: Boolean, true means include user-data.
    """
    tarfile = os.path.abspath(tarfile)
    date = datetime.utcnow().date().strftime('%Y-%m-%d')
    log_dir = 'cloud-init-logs-{0}'.format(date)
    with tempdir(dir='/tmp') as tmp_dir:
        log_dir = os.path.join(tmp_dir, log_dir)
        _write_command_output_to_file(
            ['dpkg-query', '--show', "-f=${Version}\n", 'cloud-init'],
            os.path.join(log_dir, 'version'))
        _write_command_output_to_file(
            ['dmesg'], os.path.join(log_dir, 'dmesg.txt'))
        _write_command_output_to_file(
            ['journalctl', '-o', 'short-precise'],
            os.path.join(log_dir, 'journal.txt'))
        for log in CLOUDINIT_LOGS:
            copy(log, log_dir)
        if include_userdata:
            copy(USER_DATA_FILE, log_dir)
        run_dir = os.path.join(log_dir, 'run')
        ensure_dir(run_dir)
        shutil.copytree(CLOUDINIT_RUN_DIR, os.path.join(run_dir, 'cloud-init'))
        with chdir(tmp_dir):
            subp(['tar', 'czvf', tarfile, log_dir.replace(tmp_dir + '/', '')])


def handle_collect_logs_args(name, args):
    """Handle calls to 'cloud-init collect-logs' as a subcommand."""
    collect_logs(args.tarfile, args.userdata)


def main():
    """Tool to collect and tar all cloud-init related logs."""
    parser = get_parser()
    handle_collect_logs_args('collect-logs', parser.parse_args())
    return 0


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab
