#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'collect-logs' utility and handler to include in cloud-init cmd."""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.stages import Init
from cloudinit.subp import ProcessExecutionError, subp
from cloudinit.temp_utils import tempdir
from cloudinit.util import (
    chdir,
    copy,
    ensure_dir,
    get_config_logfiles,
    write_file,
)


class LogPaths(NamedTuple):
    userdata_raw: str
    cloud_data: str
    run_dir: str
    instance_data_sensitive: str


def get_log_paths(init: Optional[Init] = None) -> LogPaths:
    """Return a Paths object based on the system configuration on disk."""
    paths = init.paths if init else read_cfg_paths()
    return LogPaths(
        userdata_raw=paths.get_ipath_cur("userdata_raw"),
        cloud_data=paths.get_cpath("data"),
        run_dir=paths.run_dir,
        instance_data_sensitive=paths.lookups["instance_data_sensitive"],
    )


class ApportFile(NamedTuple):
    path: str
    label: str


INSTALLER_APPORT_SENSITIVE_FILES = [
    ApportFile(
        "/var/log/installer/autoinstall-user-data", "AutoInstallUserData"
    ),
    ApportFile("/autoinstall.yaml", "AutoInstallYAML"),
    ApportFile("/etc/cloud/cloud.cfg.d/99-installer.cfg", "InstallerCloudCfg"),
]

INSTALLER_APPORT_FILES = [
    ApportFile("/var/log/installer/ubuntu_desktop_installer.log", "UdiLog"),
    ApportFile(
        "/var/log/installer/subiquity-server-debug.log", "SubiquityServerDebug"
    ),
    ApportFile(
        "/var/log/installer/subiquity-client-debug.log", "SubiquityClientDebug"
    ),
    ApportFile("/var/log/installer/curtin-install.log", "CurtinLog"),
    # Legacy single curtin config < 22.1
    ApportFile(
        "/var/log/installer/subiquity-curtin-install.conf",
        "CurtinInstallConfig",
    ),
    ApportFile(
        "/var/log/installer/curtin-install/subiquity-initial.conf",
        "CurtinConfigInitial",
    ),
    ApportFile(
        "/var/log/installer/curtin-install/subiquity-curthooks.conf",
        "CurtinConfigCurtHooks",
    ),
    ApportFile(
        "/var/log/installer/curtin-install/subiquity-extract.conf",
        "CurtinConfigExtract",
    ),
    ApportFile(
        "/var/log/installer/curtin-install/subiquity-partitioning.conf",
        "CurtinConfigPartitioning",
    ),
    # Legacy curtin < 22.1 curtin error tar path
    ApportFile("/var/log/installer/curtin-error-logs.tar", "CurtinError"),
    ApportFile("/var/log/installer/curtin-errors.tar", "CurtinError"),
    ApportFile("/var/log/installer/block/probe-data.json", "ProbeData"),
]


def get_parser(parser=None):
    """Build or extend and arg parser for collect-logs utility.

    @param parser: Optional existing ArgumentParser instance representing the
        collect-logs subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog="collect-logs",
            description="Collect and tar all cloud-init debug info",
        )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        dest="verbosity",
        help="Be more verbose.",
    )
    parser.add_argument(
        "--tarfile",
        "-t",
        default="cloud-init.tar.gz",
        help=(
            "The tarfile to create containing all collected logs."
            " Default: cloud-init.tar.gz"
        ),
    )
    parser.add_argument(
        "--include-userdata",
        "-u",
        default=False,
        action="store_true",
        dest="userdata",
        help=(
            "Optionally include user-data from {0} which could contain"
            " sensitive information.".format(get_log_paths().userdata_raw)
        ),
    )
    return parser


def _get_copytree_ignore_files(paths: LogPaths):
    """Return a list of files to ignore for /run/cloud-init directory"""
    ignored_files = [
        "hook-hotplug-cmd",  # named pipe for hotplug
    ]
    if os.getuid() != 0:
        # Ignore root-permissioned files
        ignored_files.append(paths.instance_data_sensitive)
    return ignored_files


def _write_command_output_to_file(cmd, filename, msg, verbosity):
    """Helper which runs a command and writes output or error to filename."""
    ensure_dir(os.path.dirname(filename))
    try:
        output = subp(cmd).stdout
    except ProcessExecutionError as e:
        write_file(filename, str(e))
        _debug("collecting %s failed.\n" % msg, 1, verbosity)
    else:
        write_file(filename, output)
        _debug("collected %s\n" % msg, 1, verbosity)
        return output


def _stream_command_output_to_file(cmd, filename, msg, verbosity):
    """Helper which runs a command and writes output or error to filename."""
    ensure_dir(os.path.dirname(filename))
    try:
        with open(filename, "w") as f:
            subprocess.call(cmd, stdout=f, stderr=f)  # nosec B603
    except OSError as e:
        write_file(filename, str(e))
        _debug("collecting %s failed.\n" % msg, 1, verbosity)
    else:
        _debug("collected %s\n" % msg, 1, verbosity)


def _debug(msg, level, verbosity):
    if level <= verbosity:
        sys.stderr.write(msg)


def _collect_file(path, out_dir, verbosity):
    if os.path.isfile(path):
        copy(path, out_dir)
        _debug("collected file: %s\n" % path, 1, verbosity)
    else:
        _debug("file %s did not exist\n" % path, 2, verbosity)


def _collect_installer_logs(
    log_dir: str, include_userdata: bool, verbosity: int
):
    """Obtain subiquity logs and config files."""
    for src_file in INSTALLER_APPORT_FILES:
        destination_dir = Path(log_dir + src_file.path).parent
        if not destination_dir.exists():
            ensure_dir(str(destination_dir))
        _collect_file(src_file.path, str(destination_dir), verbosity)
    if include_userdata:
        for src_file in INSTALLER_APPORT_SENSITIVE_FILES:
            destination_dir = Path(log_dir + src_file.path).parent
            if not destination_dir.exists():
                ensure_dir(str(destination_dir))
            _collect_file(src_file.path, str(destination_dir), verbosity)


def _collect_version_info(log_dir: str, verbosity: int):
    version = _write_command_output_to_file(
        cmd=["cloud-init", "--version"],
        filename=os.path.join(log_dir, "version"),
        msg="cloud-init --version",
        verbosity=verbosity,
    )
    dpkg_ver = _write_command_output_to_file(
        cmd=["dpkg-query", "--show", "-f=${Version}\n", "cloud-init"],
        filename=os.path.join(log_dir, "dpkg-version"),
        msg="dpkg version",
        verbosity=verbosity,
    )
    if not version:
        version = dpkg_ver if dpkg_ver else "not-available"
    _debug("collected cloud-init version: %s\n" % version, 1, verbosity)


def _collect_system_logs(log_dir: str, verbosity: int):
    _stream_command_output_to_file(
        cmd=["dmesg"],
        filename=os.path.join(log_dir, "dmesg.txt"),
        msg="dmesg output",
        verbosity=verbosity,
    )
    _stream_command_output_to_file(
        cmd=["journalctl", "--boot=0", "-o", "short-precise"],
        filename=os.path.join(log_dir, "journal.txt"),
        msg="systemd journal of current boot",
        verbosity=verbosity,
    )


def _collect_cloudinit_logs(
    log_dir: str,
    verbosity: int,
    init: Init,
    paths: LogPaths,
    include_userdata: bool,
):
    for log in get_config_logfiles(init.cfg):
        _collect_file(log, log_dir, verbosity)
    if include_userdata:
        user_data_file = paths.userdata_raw
        _collect_file(user_data_file, log_dir, verbosity)


def _collect_run_dir(log_dir: str, verbosity: int, paths: LogPaths):
    run_dir = os.path.join(log_dir, "run")
    ensure_dir(run_dir)
    if os.path.exists(paths.run_dir):
        try:
            shutil.copytree(
                paths.run_dir,
                os.path.join(run_dir, "cloud-init"),
                ignore=lambda _, __: _get_copytree_ignore_files(paths),
            )
        except shutil.Error as e:
            sys.stderr.write("Failed collecting file(s) due to error:\n")
            sys.stderr.write(str(e) + "\n")
        _debug("collected dir %s\n" % paths.run_dir, 1, verbosity)
    else:
        _debug(
            "directory '%s' did not exist\n" % paths.run_dir,
            1,
            verbosity,
        )
    if os.path.exists(os.path.join(paths.run_dir, "disabled")):
        # Fallback to grab previous cloud/data
        cloud_data_dir = Path(paths.cloud_data)
        if cloud_data_dir.exists():
            shutil.copytree(
                str(cloud_data_dir),
                Path(log_dir + str(cloud_data_dir)),
            )


def collect_logs(
    tarfile: str, include_userdata: bool, verbosity: int = 0
) -> int:
    """Collect all cloud-init logs and tar them up into the provided tarfile.

    @param tarfile: The path of the tar-gzipped file to create.
    @param include_userdata: Boolean, true means include user-data.
    @return: 0 on success, 1 on failure.
    """
    if include_userdata and os.getuid() != 0:
        sys.stderr.write(
            "To include userdata, root user is required."
            " Try sudo cloud-init collect-logs\n"
        )
        return 1

    tarfile = os.path.abspath(tarfile)
    log_dir = (
        datetime.now(timezone.utc).date().strftime("cloud-init-logs-%Y-%m-%d")
    )
    with tempdir(dir="/tmp") as tmp_dir:
        log_dir = os.path.join(tmp_dir, log_dir)
        init = Init(ds_deps=[])
        init.read_cfg()
        paths = get_log_paths(init)

        _collect_version_info(log_dir, verbosity)
        _collect_system_logs(log_dir, verbosity)
        _collect_cloudinit_logs(
            log_dir, verbosity, init, paths, include_userdata
        )
        _collect_installer_logs(log_dir, include_userdata, verbosity)
        _collect_run_dir(log_dir, verbosity, paths)
        with chdir(tmp_dir):
            subp(["tar", "czvf", tarfile, log_dir.replace(f"{tmp_dir}/", "")])
    sys.stderr.write("Wrote %s\n" % tarfile)
    return 0


def handle_collect_logs_args(name, args):
    """Handle calls to 'cloud-init collect-logs' as a subcommand."""
    return collect_logs(
        tarfile=args.tarfile,
        include_userdata=args.userdata,
        verbosity=args.verbosity,
    )


def main():
    """Tool to collect and tar all cloud-init related logs."""
    parser = get_parser()
    return handle_collect_logs_args("collect-logs", parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
