#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'status' utility and handler as part of cloud-init command line."""

import argparse
import enum
import json
import os
import sys
from copy import deepcopy
from time import gmtime, sleep, strftime
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from cloudinit import safeyaml, subp
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.distros import uses_systemd
from cloudinit.helpers import Paths
from cloudinit.util import get_cmdline, load_json, load_text_file

CLOUDINIT_DISABLED_FILE = "/etc/cloud/cloud-init.disabled"


@enum.unique
class RunningStatus(enum.Enum):
    """Enum representing user-visible cloud-init application status."""

    NOT_STARTED = "not started"
    RUNNING = "running"
    DONE = "done"
    DISABLED = "disabled"


@enum.unique
class ConditionStatus(enum.Enum):
    """Enum representing user-visible cloud-init condition status."""

    ERROR = "error"  # cloud-init exited abnormally
    DEGRADED = "degraded"  # we have warnings
    PEACHY = "healthy"  # internal names can be fun, right?


@enum.unique
class EnabledStatus(enum.Enum):
    """Enum representing user-visible cloud-init boot status codes."""

    DISABLED_BY_GENERATOR = "disabled-by-generator"
    DISABLED_BY_KERNEL_CMDLINE = "disabled-by-kernel-command-line"
    DISABLED_BY_MARKER_FILE = "disabled-by-marker-file"
    DISABLED_BY_ENV_VARIABLE = "disabled-by-environment-variable"
    ENABLED_BY_GENERATOR = "enabled-by-generator"
    ENABLED_BY_KERNEL_CMDLINE = "enabled-by-kernel-command-line"
    ENABLED_BY_SYSVINIT = "enabled-by-sysvinit"
    UNKNOWN = "unknown"


DISABLED_BOOT_CODES = frozenset(
    [
        EnabledStatus.DISABLED_BY_GENERATOR,
        EnabledStatus.DISABLED_BY_KERNEL_CMDLINE,
        EnabledStatus.DISABLED_BY_MARKER_FILE,
        EnabledStatus.DISABLED_BY_ENV_VARIABLE,
    ]
)


class StatusDetails(NamedTuple):
    running_status: RunningStatus
    condition_status: ConditionStatus
    boot_status_code: EnabledStatus
    description: str
    errors: List[str]
    recoverable_errors: Dict[str, List[str]]
    last_update: str
    datasource: Optional[str]
    v1: Dict[str, Dict]


TABULAR_LONG_TMPL = """\
extended_status: {extended_status}
boot_status_code: {boot_code}
{last_update}detail: {description}
errors:{errors}
recoverable_errors:{recoverable_errors}"""


def query_systemctl(
    systemctl_args: List[str],
    *,
    wait: bool,
) -> str:
    """Query systemd with retries and return output."""
    while True:
        try:
            return subp.subp(["systemctl", *systemctl_args]).stdout.strip()
        except subp.ProcessExecutionError:
            if not wait:
                raise
            sleep(0.25)


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


def translate_status(
    running: RunningStatus, condition: ConditionStatus
) -> Tuple[str, str]:
    """Translate running and condition status to human readable strings.

    Returns (status, extended_status).
    Much of this is for backwards compatibility
    """
    # If we're done and have errors, we're in an error state
    if condition == ConditionStatus.ERROR:
        return "error", f"{condition.value} - {running.value}"
    # Handle the "degraded done" and "degraded running" states
    elif condition == ConditionStatus.DEGRADED and running in [
        RunningStatus.DONE,
        RunningStatus.RUNNING,
    ]:
        return running.value, f"{condition.value} {running.value}"
    return running.value, running.value


def print_status(args, details: StatusDetails):
    """Print status out to the CLI."""
    status, extended_status = translate_status(
        details.running_status, details.condition_status
    )
    details_dict: Dict[str, Any] = {
        "datasource": details.datasource,
        "boot_status_code": details.boot_status_code.value,
        "status": status,
        "extended_status": extended_status,
        "detail": details.description,
        "errors": details.errors,
        "recoverable_errors": details.recoverable_errors,
        "last_update": details.last_update,
        **details.v1,
    }
    if args.format == "tabular":
        prefix = "\n" if args.wait else ""

        # For backwards compatibility, don't report degraded status here,
        # extended_status key reports the complete status (includes degraded)
        state = details_dict["status"]
        print(f"{prefix}status: {state}")
        if args.long:
            if details_dict.get("last_update"):
                last_update = f"last_update: {details_dict['last_update']}\n"
            else:
                last_update = ""
            errors_output = (
                "\n\t- " + "\n\t- ".join(details_dict["errors"])
                if details_dict["errors"]
                else " []"
            )
            recoverable_errors_output = (
                "\n"
                + "\n".join(
                    [
                        f"{k}:\n\t- "
                        + "\n\t- ".join([i.replace("\n", " ") for i in v])
                        for k, v in details_dict["recoverable_errors"].items()
                    ]
                )
                if details_dict["recoverable_errors"]
                else " {}"
            )
            print(
                TABULAR_LONG_TMPL.format(
                    extended_status=details_dict["extended_status"],
                    prefix=prefix,
                    boot_code=details_dict["boot_status_code"],
                    description=details_dict["detail"],
                    last_update=last_update,
                    errors=errors_output,
                    recoverable_errors=recoverable_errors_output,
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


def handle_status_args(name, args) -> int:
    """Handle calls to 'cloud-init status' as a subcommand."""
    # Read configured paths
    paths = read_cfg_paths()
    details = get_status_details(paths, args.wait)
    if args.wait:
        while details.running_status in (
            RunningStatus.NOT_STARTED,
            RunningStatus.RUNNING,
        ):
            if args.format == "tabular":
                sys.stdout.write(".")
                sys.stdout.flush()
            details = get_status_details(paths, args.wait)
            sleep(0.25)

    print_status(args, details)

    # Hard error
    if details.condition_status == ConditionStatus.ERROR:
        return 1
    # Recoverable error
    elif details.condition_status == ConditionStatus.DEGRADED:
        return 2
    return 0


def _disabled_via_environment(wait) -> bool:
    """Return whether cloud-init is disabled via environment variable."""
    try:
        env = query_systemctl(["show-environment"], wait=wait)
    except subp.ProcessExecutionError:
        env = ""
    return "cloud-init=disabled" in env


def get_bootstatus(disable_file, paths, wait) -> Tuple[EnabledStatus, str]:
    """Report whether cloud-init current boot status

    @param disable_file: The path to the cloud-init disable file.
    @param paths: An initialized cloudinit.helpers.Paths object.
    @param wait: If user has indicated to wait for cloud-init to complete.
    @returns: A tuple containing (code, reason) about cloud-init's status and
    why.
    """
    cmdline_parts = get_cmdline().split()
    if not uses_systemd():
        bootstatus_code = EnabledStatus.ENABLED_BY_SYSVINIT
        reason = "Cloud-init enabled on sysvinit"
    elif "cloud-init=enabled" in cmdline_parts:
        bootstatus_code = EnabledStatus.ENABLED_BY_KERNEL_CMDLINE
        reason = "Cloud-init enabled by kernel command line cloud-init=enabled"
    elif os.path.exists(disable_file):
        bootstatus_code = EnabledStatus.DISABLED_BY_MARKER_FILE
        reason = "Cloud-init disabled by {0}".format(disable_file)
    elif "cloud-init=disabled" in cmdline_parts:
        bootstatus_code = EnabledStatus.DISABLED_BY_KERNEL_CMDLINE
        reason = "Cloud-init disabled by kernel parameter cloud-init=disabled"
    elif "cloud-init=disabled" in os.environ.get("KERNEL_CMDLINE", "") or (
        uses_systemd() and _disabled_via_environment(wait=wait)
    ):
        bootstatus_code = EnabledStatus.DISABLED_BY_ENV_VARIABLE
        reason = (
            "Cloud-init disabled by environment variable "
            "KERNEL_CMDLINE=cloud-init=disabled"
        )
    elif os.path.exists(os.path.join(paths.run_dir, "disabled")):
        bootstatus_code = EnabledStatus.DISABLED_BY_GENERATOR
        reason = "Cloud-init disabled by cloud-init-generator"
    elif os.path.exists(os.path.join(paths.run_dir, "enabled")):
        bootstatus_code = EnabledStatus.ENABLED_BY_GENERATOR
        reason = "Cloud-init enabled by systemd cloud-init-generator"
    else:
        bootstatus_code = EnabledStatus.UNKNOWN
        reason = "Systemd generator may not have run yet."
    return (bootstatus_code, reason)


def is_cloud_init_enabled() -> bool:
    return (
        get_status_details(read_cfg_paths()).boot_status_code
        not in DISABLED_BOOT_CODES
    )


def systemd_failed(wait: bool) -> bool:
    """Return if systemd units report a cloud-init error."""
    for service in [
        "cloud-final.service",
        "cloud-config.service",
        "cloud-init.service",
        "cloud-init-local.service",
    ]:
        try:
            stdout = query_systemctl(
                [
                    "show",
                    "--property=ActiveState,UnitFileState,SubState,MainPID",
                    service,
                ],
                wait=wait,
            )
        except subp.ProcessExecutionError as e:
            # Systemd isn't ready, assume the same state
            print(
                "Failed to get status from systemd. "
                "Cloud-init status may be inaccurate. "
                f"Error from systemctl: {e.stderr}",
                file=sys.stderr,
            )
            return False
        states = dict(
            [[x.strip() for x in r.split("=")] for r in stdout.splitlines()]
        )
        if not (
            states["UnitFileState"].startswith("enabled")
            or states["UnitFileState"] == "static"
        ):
            # Individual services should not get disabled
            return True
        elif states["ActiveState"] == "active":
            if states["SubState"] == "exited":
                # Service exited normally, nothing interesting from systemd
                continue
            elif states["SubState"] == "running" and states["MainPID"] == "0":
                # Service is active, substate still reports running due to
                # daemon or background process spawned by CGroup/slice still
                # running. MainPID being set back to 0 means control of the
                # service/unit has exited in this case and
                # "the process is no longer around".
                return False
        elif (
            states["ActiveState"] == "failed" or states["SubState"] == "failed"
        ):
            return True
        # If we made it here, our unit is enabled and it hasn't exited
        # normally or exited with failure, so it is still running.
        return False
    # All services exited normally or aren't enabled, so don't report
    # any particular status based on systemd.
    return False


def is_running(status_file, result_file) -> bool:
    """Return True if cloud-init is running."""
    return os.path.exists(status_file) and not os.path.exists(result_file)


def get_running_status(
    status_file, result_file, boot_status_code, latest_event
) -> RunningStatus:
    """Return the running status of cloud-init."""
    if boot_status_code in DISABLED_BOOT_CODES:
        return RunningStatus.DISABLED
    elif is_running(status_file, result_file):
        return RunningStatus.RUNNING
    elif latest_event > 0:
        return RunningStatus.DONE
    else:
        return RunningStatus.NOT_STARTED


def get_datasource(status_v1) -> str:
    """Get the datasource from status.json.

    Return a lowercased non-prefixed version. So "DataSourceEc2" becomes "ec2"
    """
    datasource = status_v1.get("datasource", "")
    if datasource:
        ds, _, _ = datasource.partition(" ")
        datasource = ds.lower().replace("datasource", "")
    return datasource


def get_description(status_v1, boot_description):
    """Return a description of the current status.

    If we have a datasource, return that. If we're running in a particular
    stage, return that. Otherwise, return the boot_description.
    """
    datasource = status_v1.get("datasource")
    if datasource:
        return datasource
    elif status_v1.get("stage"):
        return f"Running in stage: {status_v1['stage']}"
    else:
        return boot_description


def get_latest_event(status_v1):
    """Return the latest event time from status_v1."""
    latest_event = 0
    for stage_info in status_v1.values():
        if isinstance(stage_info, dict):
            latest_event = max(
                latest_event,
                stage_info.get("start") or 0,
                stage_info.get("finished") or 0,
            )
    return latest_event


def get_errors(status_v1) -> Tuple[List, Dict]:
    """Return a list of errors and recoverable_errors from status_v1."""
    errors = []
    recoverable_errors = {}
    for _key, stage_info in sorted(status_v1.items()):
        if isinstance(stage_info, dict):
            errors.extend(stage_info.get("errors", []))

            # Aggregate recoverable_errors from all stages
            current_recoverable_errors = stage_info.get(
                "recoverable_errors", {}
            )
            for err_type in current_recoverable_errors.keys():
                if err_type not in recoverable_errors:
                    recoverable_errors[err_type] = deepcopy(
                        current_recoverable_errors[err_type]
                    )
                else:
                    recoverable_errors[err_type].extend(
                        current_recoverable_errors[err_type]
                    )
    return errors, recoverable_errors


def get_status_details(
    paths: Optional[Paths] = None, wait: bool = False
) -> StatusDetails:
    """Return a dict with status, details and errors.

    @param paths: An initialized cloudinit.helpers.paths object.
    @param wait: If user has indicated to wait for cloud-init to complete.

    Values are obtained from parsing paths.run_dir/status.json.
    """
    condition_status = ConditionStatus.PEACHY
    paths = paths or read_cfg_paths()
    status_file = os.path.join(paths.run_dir, "status.json")
    result_file = os.path.join(paths.run_dir, "result.json")
    boot_status_code, boot_description = get_bootstatus(
        CLOUDINIT_DISABLED_FILE, paths, wait
    )
    status_v1 = {}
    if os.path.exists(status_file):
        status_v1 = load_json(load_text_file(status_file)).get("v1", {})

    datasource = get_datasource(status_v1)
    description = get_description(status_v1, boot_description)

    latest_event = get_latest_event(status_v1)
    last_update = (
        strftime("%a, %d %b %Y %H:%M:%S %z", gmtime(latest_event))
        if latest_event
        else ""
    )

    errors, recoverable_errors = get_errors(status_v1)
    if errors:
        condition_status = ConditionStatus.ERROR
    elif recoverable_errors:
        condition_status = ConditionStatus.DEGRADED

    running_status = get_running_status(
        status_file, result_file, boot_status_code, latest_event
    )

    if (
        running_status == RunningStatus.RUNNING
        and uses_systemd()
        and systemd_failed(wait=wait)
    ):
        running_status = RunningStatus.DONE
        condition_status = ConditionStatus.ERROR
        description = "Failed due to systemd unit failure"
        errors.append(
            "Failed due to systemd unit failure. Ensure all cloud-init "
            "services are enabled, and check 'systemctl' or 'journalctl' "
            "for more information."
        )

    # this key is a duplicate
    status_v1.pop("datasource", None)

    return StatusDetails(
        running_status,
        condition_status,
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
