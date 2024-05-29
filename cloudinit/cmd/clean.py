#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'clean' utility and handler as part of cloud-init command line."""

import argparse
import glob
import os
import sys

from cloudinit import settings
from cloudinit.distros import uses_systemd
from cloudinit.net.netplan import CLOUDINIT_NETPLAN_FILE
from cloudinit.stages import Init
from cloudinit.subp import ProcessExecutionError, runparts, subp
from cloudinit.util import (
    del_dir,
    del_file,
    error,
    get_config_logfiles,
    is_link,
    write_file,
)

ETC_MACHINE_ID = "/etc/machine-id"
GEN_NET_CONFIG_FILES = [
    CLOUDINIT_NETPLAN_FILE,
    "/etc/NetworkManager/conf.d/99-cloud-init.conf",
    "/etc/NetworkManager/conf.d/30-cloud-init-ip6-addr-gen-mode.conf",
    "/etc/NetworkManager/system-connections/cloud-init-*.nmconnection",
    "/etc/systemd/network/10-cloud-init-*.network",
    "/etc/network/interfaces.d/50-cloud-init.cfg",
]
GEN_SSH_CONFIG_FILES = [
    "/etc/ssh/sshd_config.d/50-cloud-init.conf",
]


def get_parser(parser=None):
    """Build or extend an arg parser for clean utility.

    @param parser: Optional existing ArgumentParser instance representing the
        clean subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog="clean",
            description=(
                "Remove logs, configs and artifacts so cloud-init re-runs "
                "on a clean system"
            ),
        )
    parser.add_argument(
        "-l",
        "--logs",
        action="store_true",
        default=False,
        dest="remove_logs",
        help="Remove cloud-init logs.",
    )
    parser.add_argument(
        "--machine-id",
        action="store_true",
        default=False,
        help=(
            "Set /etc/machine-id to 'uninitialized\n' for golden image"
            "creation. On next boot, systemd generates a new machine-id."
            " Remove /etc/machine-id on non-systemd environments."
        ),
    )
    parser.add_argument(
        "-r",
        "--reboot",
        action="store_true",
        default=False,
        help="Reboot system after logs are cleaned so cloud-init re-runs.",
    )
    parser.add_argument(
        "-s",
        "--seed",
        action="store_true",
        default=False,
        dest="remove_seed",
        help="Remove cloud-init seed directory /var/lib/cloud/seed.",
    )
    parser.add_argument(
        "-c",
        "--configs",
        choices=[
            "all",
            "ssh_config",
            "network",
        ],
        default=[],
        nargs="+",
        dest="remove_config",
        help="Remove cloud-init generated config files of a certain type."
        " Config types: all, ssh_config, network",
    )
    return parser


def remove_artifacts(init, remove_logs, remove_seed=False, remove_config=None):
    """Helper which removes artifacts dir and optionally log files.

    @param: init: Init object to use
    @param: remove_logs: Boolean. Set True to delete the cloud_dir path. False
        preserves them.
    @param: remove_seed: Boolean. Set True to also delete seed subdir in
        paths.cloud_dir.
    @param: remove_config: List of strings.
        Can be any of: all, network, ssh_config.
    @returns: 0 on success, 1 otherwise.
    """
    init.read_cfg()
    if remove_logs:
        for log_file in get_config_logfiles(init.cfg):
            del_file(log_file)
    if remove_config and set(remove_config).intersection(["all", "network"]):
        for path in GEN_NET_CONFIG_FILES:
            for conf in glob.glob(path):
                del_file(conf)
    if remove_config and set(remove_config).intersection(
        ["all", "ssh_config"]
    ):
        for conf in GEN_SSH_CONFIG_FILES:
            del_file(conf)

    if not os.path.isdir(init.paths.cloud_dir):
        return 0  # Artifacts dir already cleaned
    seed_path = os.path.join(init.paths.cloud_dir, "seed")
    for path in glob.glob("%s/*" % init.paths.cloud_dir):
        if path == seed_path and not remove_seed:
            continue
        try:
            if os.path.isdir(path) and not is_link(path):
                del_dir(path)
            else:
                del_file(path)
        except OSError as e:
            error("Could not remove {0}: {1}".format(path, str(e)))
            return 1
    try:
        runparts(settings.CLEAN_RUNPARTS_DIR)
    except Exception as e:
        error(
            f"Failure during run-parts of {settings.CLEAN_RUNPARTS_DIR}: {e}"
        )
        return 1
    return 0


def handle_clean_args(name, args):
    """Handle calls to 'cloud-init clean' as a subcommand."""
    init = Init(ds_deps=[])
    exit_code = remove_artifacts(
        init, args.remove_logs, args.remove_seed, args.remove_config
    )
    if args.machine_id:
        if uses_systemd():
            # Systemd v237 and later will create a new machine-id on next boot
            write_file(ETC_MACHINE_ID, "uninitialized\n", mode=0o444)
        else:
            # Non-systemd like FreeBSD regen machine-id when file is absent
            del_file(ETC_MACHINE_ID)
    if exit_code == 0 and args.reboot:
        cmd = init.distro.shutdown_command(
            mode="reboot", delay="now", message=None
        )
        try:
            subp(cmd, capture=False)
        except ProcessExecutionError as e:
            error(
                'Could not reboot this system using "{0}": {1}'.format(
                    cmd, str(e)
                )
            )
            exit_code = 1
    return exit_code


def main():
    """Tool to collect and tar all cloud-init related logs."""
    parser = get_parser()
    sys.exit(handle_clean_args("clean", parser.parse_args()))


if __name__ == "__main__":
    main()
