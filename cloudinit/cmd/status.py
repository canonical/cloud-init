#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'status' utility and handler as part of cloud-init commandline."""

import argparse
import enum
import json
import os
import sys
from copy import deepcopy
from time import gmtime, sleep, strftime
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from cloudinit import safeyaml, subp
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.distros import uses_systemd
from cloudinit.helpers import Paths
from cloudinit.util import get_cmdline, load_json, load_text_file

CLOUDINIT_DISABLED_FILE = "/etc/cloud/cloud-init.disabled"


# customer visible status messages
@enum.unique
class UXAppStatus(enum.Enum):
    """Enum representing user-visible cloud-init application status."""

    NOT_RUN = "not run"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    DEGRADED_DONE = "degraded done"
    DEGRADED_RUNNING = "degraded running"
    DISABLED = "disabled"


# Extend states when degraded
UXAppStatusDegradedMap = {
    UXAppStatus.RUNNING: UXAppStatus.DEGRADED_RUNNING,
    UXAppStatus.DONE: UXAppStatus.DEGRADED_DONE,
}

# Map extended states back to simplified states
UXAppStatusDegradedMapCompat = {
    UXAppStatus.DEGRADED_RUNNING: UXAppStatus.RUNNING,
    UXAppStatus.DEGRADED_DONE: UXAppStatus.DONE,
}


@enum.unique
class UXAppBootStatusCode(enum.Enum):
    """Enum representing user-visible cloud-init boot status codes."""

    DISABLED_BY_GENERATOR = "disabled-by-generator"
    DISABLED_BY_KERNEL_CMDLINE = "disabled-by-kernel-cmdline"
    DISABLED_BY_MARKER_FILE = "disabled-by-marker-file"
    DISABLED_BY_ENV_VARIABLE = "disabled-by-environment-variable"
    ENABLED_BY_GENERATOR = "enabled-by-generator"
    ENABLED_BY_KERNEL_CMDLINE = "enabled-by-kernel-cmdline"
    ENABLED_BY_SYSVINIT = "enabled-by-sysvinit"
    UNKNOWN = "unknown"


DISABLED_BOOT_CODES = frozenset(
    [
        UXAppBootStatusCode.DISABLED_BY_GENERATOR,
        UXAppBootStatusCode.DISABLED_BY_KERNEL_CMDLINE,
        UXAppBootStatusCode.DISABLED_BY_MARKER_FILE,
        UXAppBootStatusCode.DISABLED_BY_ENV_VARIABLE,
    ]
)


class StatusDetails(NamedTuple):
    status: UXAppStatus
    boot_status_code: UXAppBootStatusCode
    description: str
    errors: List[str]
    recoverable_errors: Dict[str, List[str]]
    last_update: str
    datasource: Optional[str]
    v1: Dict[str, Dict]


TABULAR_LONG_TMPL = """\
extended_status: {extended_status}
boot_status_code: {boot_code}
{last_update}detail:
{description}"""


def get_parser(parser=None):
    """Build or extend an arg parser for status utility.

    @param parser: Optional existing ArgumentParser instance representing the
        status subcommand which will be extended to support the args of
        this utility.

    @returns: ArgumentParser with proper argument configuration.
    """
    if not parser:
        parser = argparse.ArgumentParser(
            prog="status", description="Report run status of cloud init"
        )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "tabular", "yaml"],
        default="tabular",
        help="Specify output format for cloud-id (default: tabular)",
    )
    parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        default=False,
        help=(
            "Report long format of statuses including run stage name and"
            " error messages"
        ),
    )
    parser.add_argument(
        "-w",
        "--wait",
        action="store_true",
        default=False,
        help="Block waiting on cloud-init to complete",
    )
    return parser


def handle_status_args(name, args) -> int:
    """Handle calls to 'cloud-init status' as a subcommand."""
    # Read configured paths
    paths = read_cfg_paths()
    details = get_status_details(paths, args.wait)
    if args.wait:
        while details.status in (
            UXAppStatus.NOT_RUN,
            UXAppStatus.RUNNING,
            UXAppStatus.DEGRADED_RUNNING,
        ):
            if args.format == "tabular":
                sys.stdout.write(".")
                sys.stdout.flush()
            details = get_status_details(paths, args.wait)
            sleep(0.25)
    details_dict: Dict[str, Union[None, str, List[str], Dict[str, Any]]] = {
        "datasource": details.datasource,
        "boot_status_code": details.boot_status_code.value,
        "status": UXAppStatusDegradedMapCompat.get(
            details.status, details.status
        ).value,
        "extended_status": details.status.value,
        "detail": details.description,
        "errors": details.errors,
        "recoverable_errors": details.recoverable_errors,
        "last_update": details.last_update,
        **details.v1,
    }

    if args.format == "tabular":
        prefix = "\n" if args.wait else ""

        # For backwards compatability, don't report degraded status here,
        # extended_status key reports the complete status (includes degraded)
        state = UXAppStatusDegradedMapCompat.get(
            details.status, details.status
        ).value
        print(f"{prefix}status: {state}")
        if args.long:
            if details.last_update:
                last_update = f"last_update: {details.last_update}\n"
            else:
                last_update = ""
            print(
                TABULAR_LONG_TMPL.format(
                    extended_status=details.status.value,
                    prefix=prefix,
                    boot_code=details.boot_status_code.value,
                    description=details.description,
                    last_update=last_update,
                )
                + (
                    "\nerrors:"
                    + (
                        "\n\t- " + "\n\t- ".join(details.errors)
                        if details.errors
                        else f" {details.errors}"
                    )
                )
                + (
                    "\nrecoverable_errors:"
                    + (
                        "\n"
                        + "\n".join(
                            [
                                f"{k}:\n\t- "
                                + "\n\t- ".join(
                                    [i.replace("\n", " ") for i in v]
                                )
                                for k, v in details.recoverable_errors.items()
                            ]
                        )
                        if details.recoverable_errors
                        else f" {details.recoverable_errors}"
                    )
                )
            )
    elif args.format == "json":
        print(
            json.dumps(  # Pretty, sorted json
                details_dict, indent=2, sort_keys=True, separators=(",", ": ")
            )
        )
    elif args.format == "yaml":
        print(safeyaml.dumps(details_dict))

    # Hard error
    if details.status == UXAppStatus.ERROR:
        return 1
    # Recoverable error
    elif details.status in UXAppStatusDegradedMap.values():
        return 2
    return 0


def get_bootstatus(disable_file, paths) -> Tuple[UXAppBootStatusCode, str]:
    """Report whether cloud-init current boot status

    @param disable_file: The path to the cloud-init disable file.
    @param paths: An initialized cloudinit.helpers.Paths object.
    @returns: A tuple containing (code, reason) about cloud-init's status and
    why.
    """
    cmdline_parts = get_cmdline().split()
    if not uses_systemd():
        bootstatus_code = UXAppBootStatusCode.ENABLED_BY_SYSVINIT
        reason = "Cloud-init enabled on sysvinit"
    elif "cloud-init=enabled" in cmdline_parts:
        bootstatus_code = UXAppBootStatusCode.ENABLED_BY_KERNEL_CMDLINE
        reason = "Cloud-init enabled by kernel command line cloud-init=enabled"
    elif os.path.exists(disable_file):
        bootstatus_code = UXAppBootStatusCode.DISABLED_BY_MARKER_FILE
        reason = "Cloud-init disabled by {0}".format(disable_file)
    elif "cloud-init=disabled" in cmdline_parts:
        bootstatus_code = UXAppBootStatusCode.DISABLED_BY_KERNEL_CMDLINE
        reason = "Cloud-init disabled by kernel parameter cloud-init=disabled"
    elif "cloud-init=disabled" in os.environ.get("KERNEL_CMDLINE", "") or (
        uses_systemd()
        and "cloud-init=disabled"
        in subp.subp(["systemctl", "show-environment"]).stdout
    ):
        bootstatus_code = UXAppBootStatusCode.DISABLED_BY_ENV_VARIABLE
        reason = (
            "Cloud-init disabled by environment variable "
            "KERNEL_CMDLINE=cloud-init=disabled"
        )
    elif os.path.exists(os.path.join(paths.run_dir, "disabled")):
        bootstatus_code = UXAppBootStatusCode.DISABLED_BY_GENERATOR
        reason = "Cloud-init disabled by cloud-init-generator"
    elif os.path.exists(os.path.join(paths.run_dir, "enabled")):
        bootstatus_code = UXAppBootStatusCode.ENABLED_BY_GENERATOR
        reason = "Cloud-init enabled by systemd cloud-init-generator"
    else:
        bootstatus_code = UXAppBootStatusCode.UNKNOWN
        reason = "Systemd generator may not have run yet."
    return (bootstatus_code, reason)


def _get_error_or_running_from_systemd() -> Optional[UXAppStatus]:
    """Get if systemd is in error or running state.

    Using systemd, we can get more fine-grained status of the
    individual unit. Determine if we're still
    running or if there's an error we haven't otherwise detected.

    If we don't detect error or running, return None as we don't want to
    report any other particular status based on systemd.
    """
    for service in [
        "cloud-final.service",
        "cloud-config.service",
        "cloud-init.service",
        "cloud-init-local.service",
    ]:
        stdout = subp.subp(
            [
                "systemctl",
                "show",
                "--property=ActiveState,UnitFileState,SubState,MainPID",
                service,
            ],
        ).stdout
        states = dict(
            [[x.strip() for x in r.split("=")] for r in stdout.splitlines()]
        )
        if not (
            states["UnitFileState"].startswith("enabled")
            or states["UnitFileState"] == "static"
        ):
            # Individual services should not get disabled
            return UXAppStatus.ERROR
        if states["ActiveState"] == "active":
            if states["SubState"] == "exited":
                # Service exited normally, nothing interesting from systemd
                continue
            elif states["SubState"] == "running" and states["MainPID"] == "0":
                # Service is active, substate still reports running due to
                # daemon or backgroud process spawned by CGroup/slice still
                # running. MainPID being set back to 0 means control of the
                # service/unit has exited in this case and
                # "the process is no longer around".
                continue
        if states["ActiveState"] == "failed" or states["SubState"] == "failed":
            # We have an error
            return UXAppStatus.ERROR
        # If we made it here, our unit is enabled and it hasn't exited
        # normally or exited with failure, so it is still running.
        return UXAppStatus.RUNNING
    # All services exited normally or aren't enabled, so don't report
    # any particular status based on systemd.
    return None


def _get_error_or_running_from_systemd_with_retry(
    existing_status: UXAppStatus, *, wait: bool
) -> Optional[UXAppStatus]:
    """Get systemd status and retry if dbus isn't ready.

    If cloud-init has determined that we're still running, then we can
    ignore the status from systemd. However, if cloud-init has detected error,
    then we should retry on systemd status so we don't incorrectly report
    error state while cloud-init is still running.
    """
    while True:
        try:
            return _get_error_or_running_from_systemd()
        except subp.ProcessExecutionError as e:
            last_exception = e
            if existing_status in (
                UXAppStatus.DEGRADED_RUNNING,
                UXAppStatus.RUNNING,
            ):
                return None
            if wait:
                sleep(0.25)
            else:
                break
    print(
        "Failed to get status from systemd. "
        "Cloud-init status may be inaccurate. ",
        f"Error from systemctl: {last_exception.stderr}",
        file=sys.stderr,
    )
    return None


def get_status_details(
    paths: Optional[Paths] = None, wait: bool = False
) -> StatusDetails:
    """Return a dict with status, details and errors.

    @param paths: An initialized cloudinit.helpers.paths object.

    Values are obtained from parsing paths.run_dir/status.json.
    """
    paths = paths or read_cfg_paths()

    status = UXAppStatus.NOT_RUN
    errors = []
    datasource: Optional[str] = ""
    status_v1 = {}

    status_file = os.path.join(paths.run_dir, "status.json")
    result_file = os.path.join(paths.run_dir, "result.json")

    boot_status_code, description = get_bootstatus(
        CLOUDINIT_DISABLED_FILE, paths
    )
    if boot_status_code in DISABLED_BOOT_CODES:
        status = UXAppStatus.DISABLED
    if os.path.exists(status_file):
        if not os.path.exists(result_file):
            status = UXAppStatus.RUNNING
        status_v1 = load_json(load_text_file(status_file)).get("v1", {})
    latest_event = 0
    recoverable_errors = {}
    for key, value in sorted(status_v1.items()):
        if key == "stage":
            if value:
                status = UXAppStatus.RUNNING
                description = "Running in stage: {0}".format(value)
        elif key == "datasource":
            if value is None:
                # If ds not yet written in status.json, then keep previous
                # description
                datasource = value
                continue
            description = value
            ds, _, _ = value.partition(" ")
            datasource = ds.lower().replace("datasource", "")
        elif isinstance(value, dict):
            errors.extend(value.get("errors", []))
            start = value.get("start") or 0
            finished = value.get("finished") or 0

            # Aggregate recoverable_errors from all stages
            current_recoverable_errors = value.get("recoverable_errors", {})
            for err_type in current_recoverable_errors.keys():
                if err_type not in recoverable_errors:
                    recoverable_errors[err_type] = deepcopy(
                        current_recoverable_errors[err_type]
                    )
                else:
                    recoverable_errors[err_type].extend(
                        current_recoverable_errors[err_type]
                    )
            if finished == 0 and start != 0:
                status = UXAppStatus.RUNNING
            event_time = max(start, finished)
            if event_time > latest_event:
                latest_event = event_time
    if errors:
        status = UXAppStatus.ERROR
    elif status == UXAppStatus.NOT_RUN and latest_event > 0:
        status = UXAppStatus.DONE
    if uses_systemd() and status not in (
        UXAppStatus.NOT_RUN,
        UXAppStatus.DISABLED,
    ):
        systemd_status = _get_error_or_running_from_systemd_with_retry(
            status, wait=wait
        )
        if systemd_status:
            status = systemd_status

    last_update = (
        strftime("%a, %d %b %Y %H:%M:%S %z", gmtime(latest_event))
        if latest_event
        else ""
    )

    if recoverable_errors:
        status = UXAppStatusDegradedMap.get(status, status)

    # this key is a duplicate
    status_v1.pop("datasource", None)
    return StatusDetails(
        status,
        boot_status_code,
        description,
        errors,
        recoverable_errors,
        last_update,
        datasource,
        status_v1,
    )


def main():
    """Tool to report status of cloud-init."""
    parser = get_parser()
    sys.exit(handle_status_args("status", parser.parse_args()))


if __name__ == "__main__":
    main()
