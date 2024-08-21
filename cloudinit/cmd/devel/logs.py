#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'collect-logs' utility and handler to include in cloud-init cmd."""

import argparse
import itertools
import logging
import os
import pathlib
import stat
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, NamedTuple, Optional, cast

from cloudinit import log
from cloudinit.stages import Init
from cloudinit.subp import ProcessExecutionError, subp
from cloudinit.temp_utils import tempdir
from cloudinit.util import copy, get_config_logfiles, write_file

LOG = cast(log.CustomLoggerType, logging.getLogger(__name__))


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


def get_parser(
    parser: Optional[argparse.ArgumentParser] = None,
) -> argparse.ArgumentParser:
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
            "DEPRECATED: This is default behavior and this flag does nothing"
        ),
    )
    parser.add_argument(
        "--redact-sensitive",
        "-r",
        default=False,
        action="store_true",
        help=(
            "Redact potentially sensitive data from logs. Sensitive data "
            "may include passwords or keys in user data and "
            "root read-only files."
        ),
    )
    return parser


def _write_command_output_to_file(
    cmd: List[str],
    file_path: pathlib.Path,
    msg: str,
) -> Optional[str]:
    """Helper which runs a command and writes output or error to filename."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = subp(cmd).stdout
    except ProcessExecutionError as e:
        write_file(file_path, str(e))
        LOG.debug("collecting %s failed.", msg)
        output = None
    else:
        write_file(file_path, output)
        LOG.debug("collected %s to file '%s'", msg, file_path.stem)
    return output


def _stream_command_output_to_file(
    cmd: List[str], file_path: pathlib.Path, msg: str
) -> None:
    """Helper which runs a command and writes output or error to filename.

    `subprocess.call` is invoked directly here to stream output to the file.
    Otherwise memory usage can be high for large outputs.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with file_path.open("w") as f:
            subprocess.call(cmd, stdout=f, stderr=f)  # nosec B603
    except OSError as e:
        write_file(file_path, str(e))
        LOG.debug("collecting %s failed.", msg)
    else:
        LOG.debug("collected %s to file '%s'", msg, file_path.stem)


def _collect_file(
    path: pathlib.Path, out_dir: pathlib.Path, include_sensitive: bool
) -> None:
    """Collect a file into what will be the tarball."""
    if path.is_file():
        if include_sensitive or path.stat().st_mode & stat.S_IROTH:
            out_dir.mkdir(parents=True, exist_ok=True)
            copy(path, out_dir)
            LOG.debug("collected file: %s", path)
        else:
            LOG.trace("sensitive file %s was not collected", path)
    else:
        LOG.trace("file %s did not exist", path)


def _collect_installer_logs(
    log_dir: pathlib.Path, include_sensitive: bool
) -> None:
    """Obtain subiquity logs and config files."""
    for src_file in INSTALLER_APPORT_FILES:
        destination_dir = pathlib.Path(log_dir, src_file.path[1:]).parent
        _collect_file(
            pathlib.Path(src_file.path),
            destination_dir,
            include_sensitive=True,  # Because this function does check
        )
    if include_sensitive:
        for src_file in INSTALLER_APPORT_SENSITIVE_FILES:
            destination_dir = pathlib.Path(log_dir, src_file.path[1:]).parent
            _collect_file(
                pathlib.Path(src_file.path),
                destination_dir,
                include_sensitive=True,  # Because this function does check
            )


def _collect_version_info(log_dir: pathlib.Path) -> None:
    """Include cloud-init version and dpkg version in the logs."""
    version = _write_command_output_to_file(
        cmd=["cloud-init", "--version"],
        file_path=log_dir / "version",
        msg="cloud-init --version",
    )
    dpkg_ver = _write_command_output_to_file(
        cmd=["dpkg-query", "--show", "-f=${Version}\n", "cloud-init"],
        file_path=log_dir / "dpkg-version",
        msg="dpkg version",
    )
    if not version:
        version = dpkg_ver or "not-available"


def _collect_system_logs(
    log_dir: pathlib.Path, include_sensitive: bool
) -> None:
    """Include dmesg and journalctl output in the logs."""
    if include_sensitive:
        _stream_command_output_to_file(
            cmd=["dmesg"],
            file_path=log_dir / "dmesg.txt",
            msg="dmesg output",
        )
    _stream_command_output_to_file(
        cmd=["journalctl", "--boot=0", "-o", "short-precise"],
        file_path=log_dir / "journal.txt",
        msg="systemd journal of current boot",
    )
    _stream_command_output_to_file(
        cmd=["journalctl", "--boot=-1", "-o", "short-precise"],
        file_path=pathlib.Path(log_dir, "journal-previous.txt"),
        msg="systemd journal of previous boot",
    )


def _get_cloudinit_logs(
    log_cfg: Dict[str, Any],
) -> Iterator[pathlib.Path]:
    """Get paths for cloud-init.log and cloud-init-output.log."""
    for path in get_config_logfiles(log_cfg):
        yield pathlib.Path(path)


def _get_etc_cloud(
    etc_cloud_dir: pathlib.Path = pathlib.Path("/etc/cloud"),
) -> Iterator[pathlib.Path]:
    """Get paths for all files in /etc/cloud.

    Excludes:
      /etc/cloud/keys because it may contain non-useful sensitive data.
      /etc/cloud/templates because we already know its contents
    """
    ignore = [
        etc_cloud_dir / "keys",
        etc_cloud_dir / "templates",
        # Captured by the installer apport files
        "99-installer.cfg",
    ]
    yield from (
        path
        for path in etc_cloud_dir.glob("**/*")
        if path.name not in ignore and path.parent not in ignore
    )


def _get_var_lib_cloud(cloud_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Get paths for files in /var/lib/cloud.

    Skip user-provided scripts, semaphores, and old instances.
    """
    return itertools.chain(
        cloud_dir.glob("data/*"),
        cloud_dir.glob("handlers/*"),
        cloud_dir.glob("seed/*"),
        (p for p in cloud_dir.glob("instance/*") if p.is_file()),
        cloud_dir.glob("instance/handlers"),
    )


def _get_run_dir(run_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Get all paths under /run/cloud-init except for hook-hotplug-cmd.

    Note that this only globs the top-level directory as there are currently
    no relevant files within subdirectories.
    """
    return (p for p in run_dir.glob("*") if p.name != "hook-hotplug-cmd")


def _collect_logs_into_tmp_dir(
    log_dir: pathlib.Path,
    log_cfg: Dict[str, Any],
    run_dir: pathlib.Path,
    cloud_dir: pathlib.Path,
    include_sensitive: bool,
) -> None:
    """Collect all cloud-init logs into the provided directory."""
    _collect_version_info(log_dir)
    _collect_system_logs(log_dir, include_sensitive)
    _collect_installer_logs(log_dir, include_sensitive)

    for logfile in _get_cloudinit_logs(log_cfg):
        # Even though log files are root read-only, the logs tarball
        # would be useless without them and we've been careful to not
        # include sensitive data in them.
        _collect_file(
            logfile,
            log_dir / pathlib.Path(logfile).parent.relative_to("/"),
            True,
        )
    for logfile in itertools.chain(
        _get_etc_cloud(),
        _get_var_lib_cloud(cloud_dir=cloud_dir),
        _get_run_dir(run_dir=run_dir),
    ):
        _collect_file(
            logfile,
            log_dir / pathlib.Path(logfile).parent.relative_to("/"),
            include_sensitive,
        )


def collect_logs(
    tarfile: str,
    log_cfg: Dict[str, Any],
    run_dir: pathlib.Path = pathlib.Path("/run/cloud-init"),
    cloud_dir: pathlib.Path = pathlib.Path("/var/lib/cloud"),
    include_sensitive: bool = True,
) -> None:
    """Collect all cloud-init logs and tar them up into the provided tarfile.

    :param tarfile: The path of the tar-gzipped file to create.
    :param log_cfg: The cloud-init base configuration containing logging cfg.
    :param run_dir: The path to the cloud-init run directory.
    :param cloud_dir: The path to the cloud-init cloud directory.
    :param include_sensitive: Boolean, true means include sensitive data.
    """
    tarfile = os.path.abspath(tarfile)
    dir_name = (
        datetime.now(timezone.utc).date().strftime("cloud-init-logs-%Y-%m-%d")
    )
    with tempdir(dir=run_dir) as tmp_dir:
        log_dir = pathlib.Path(tmp_dir, dir_name)
        _collect_logs_into_tmp_dir(
            log_dir=log_dir,
            log_cfg=log_cfg,
            run_dir=run_dir,
            cloud_dir=cloud_dir,
            include_sensitive=include_sensitive,
        )
        subp(
            [
                "tar",
                "czf",
                tarfile,
                "-C",
                tmp_dir,
                str(log_dir).replace(f"{tmp_dir}/", ""),
            ]
        )
    LOG.info("Wrote %s", tarfile)


def _setup_logger(verbosity: int) -> None:
    """Set up the logger for CLI use.

    The verbosity controls which level gets printed to stderr. By default,
    DEBUG and TRACE are hidden.
    """
    log.reset_logging()
    if verbosity == 0:
        level = logging.INFO
    elif verbosity == 1:
        level = logging.DEBUG
    else:
        level = log.TRACE
    LOG.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)


def collect_logs_cli(
    tarfile: str,
    verbosity: int = 0,
    redact_sensitive: bool = True,
    include_userdata: bool = False,
) -> None:
    """Handle calls to 'cloud-init collect-logs' as a subcommand."""
    _setup_logger(verbosity)
    if os.getuid() != 0:
        raise RuntimeError("This command must be run as root.")
    if include_userdata:
        LOG.warning(
            "The --include-userdata flag is deprecated and does nothing."
        )
    init = Init(ds_deps=[])
    init.read_cfg()

    collect_logs(
        tarfile=tarfile,
        log_cfg=init.cfg,
        run_dir=pathlib.Path(init.paths.run_dir),
        cloud_dir=pathlib.Path(init.paths.cloud_dir),
        include_sensitive=not redact_sensitive,
    )
    if not redact_sensitive:
        LOG.warning(
            "WARNING:\n"
            "Sensitive data may have been included in the collected logs.\n"
            "Please review the contents of the tarball before sharing or\n"
            "rerun with --redact-sensitive to redact sensitive data."
        )


def handle_collect_logs_args(_name: str, args: argparse.Namespace) -> int:
    """Handle the CLI interface to the module.

    Parse CLI args, redirect all exceptions to stderr, and return an exit code.
    """
    args = get_parser().parse_args()
    try:
        collect_logs_cli(
            verbosity=args.verbosity,
            tarfile=args.tarfile,
            redact_sensitive=args.redact_sensitive,
            include_userdata=args.userdata,
        )
        return 0
    except Exception as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(handle_collect_logs_args("", get_parser().parse_args()))
