# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'clean' utility and handler as part of cloud-init commandline."""

import argparse
import os
import sys

from cloudinit.stages import Init
from cloudinit.util import (
    ProcessExecutionError, chdir, del_dir, del_file, get_config_logfiles,
    is_link, subp)


def error(msg):
    sys.stderr.write("ERROR: " + msg + "\n")


def get_parser(parser=None):
    """Build or extend an arg parser for clean utility.

    @param parser: Optional existing ArgumentParser instance representing the
        clean subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog='clean',
            description=('Remove logs and artifacts so cloud-init re-runs on '
                         'a clean system'))
    parser.add_argument(
        '-l', '--logs', action='store_true', default=False, dest='remove_logs',
        help='Remove cloud-init logs.')
    parser.add_argument(
        '-r', '--reboot', action='store_true', default=False,
        help='Reboot system after logs are cleaned so cloud-init re-runs.')
    parser.add_argument(
        '-s', '--seed', action='store_true', default=False, dest='remove_seed',
        help='Remove cloud-init seed directory /var/lib/cloud/seed.')
    return parser


def remove_artifacts(remove_logs, remove_seed=False):
    """Helper which removes artifacts dir and optionally log files.

    @param: remove_logs: Boolean. Set True to delete the cloud_dir path. False
        preserves them.
    @param: remove_seed: Boolean. Set True to also delete seed subdir in
        paths.cloud_dir.
    @returns: 0 on success, 1 otherwise.
    """
    init = Init(ds_deps=[])
    init.read_cfg()
    if remove_logs:
        for log_file in get_config_logfiles(init.cfg):
            del_file(log_file)

    if not os.path.isdir(init.paths.cloud_dir):
        return 0  # Artifacts dir already cleaned
    with chdir(init.paths.cloud_dir):
        for path in os.listdir('.'):
            if path == 'seed' and not remove_seed:
                continue
            try:
                if os.path.isdir(path) and not is_link(path):
                    del_dir(path)
                else:
                    del_file(path)
            except OSError as e:
                error('Could not remove {0}: {1}'.format(path, str(e)))
                return 1
    return 0


def handle_clean_args(name, args):
    """Handle calls to 'cloud-init clean' as a subcommand."""
    exit_code = remove_artifacts(args.remove_logs, args.remove_seed)
    if exit_code == 0 and args.reboot:
        cmd = ['shutdown', '-r', 'now']
        try:
            subp(cmd, capture=False)
        except ProcessExecutionError as e:
            error(
                'Could not reboot this system using "{0}": {1}'.format(
                    cmd, str(e)))
            exit_code = 1
    return exit_code


def main():
    """Tool to collect and tar all cloud-init related logs."""
    parser = get_parser()
    sys.exit(handle_clean_args('clean', parser.parse_args()))


if __name__ == '__main__':
    main()

# vi: ts=4 expandtab
