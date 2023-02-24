#!/usr/bin/env python3

# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'status' utility and handler as part of cloud-init commandline."""

import argparse
import copy
import enum
import json
import os
import sys
from time import gmtime, sleep, strftime
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from cloudinit import safeyaml
from cloudinit.cmd.devel import read_cfg_paths
from cloudinit.distros import uses_systemd
from cloudinit.helpers import Paths
from cloudinit.util import get_cmdline, load_file, load_json

CLOUDINIT_DISABLED_FILE = "/etc/cloud/cloud-init.disabled"


# customer visible status messages
@enum.unique
class UXAppStatus(enum.Enum):
    """Enum representing user-visible cloud-init application status."""

    NOT_RUN = "not run"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    DISABLED = "disabled"


@enum.unique
class UXAppBootStatusCode(enum.Enum):
    """Enum representing user-visible cloud-init boot status codes."""

    DISABLED_BY_GENERATOR = "disabled-by-generator"
    DISABLED_BY_KERNEL_CMDLINE = "disabled-by-kernel-cmdline"
    DISABLED_BY_MARKER_FILE = "disabled-by-marker-file"
    ENABLED_BY_GENERATOR = "enabled-by-generator"
    ENABLED_BY_KERNEL_CMDLINE = "enabled-by-kernel-cmdline"
    ENABLED_BY_SYSVINIT = "enabled-by-sysvinit"
    UNKNOWN = "unknown"


DISABLED_BOOT_CODES = frozenset(
    [
        UXAppBootStatusCode.DISABLED_BY_GENERATOR,
        UXAppBootStatusCode.DISABLED_BY_KERNEL_CMDLINE,
        UXAppBootStatusCode.DISABLED_BY_MARKER_FILE,
    ]
)


class StatusDetails(NamedTuple):
    status: UXAppStatus
    boot_status_code: UXAppBootStatusCode
    description: str
    errors: List[str]
    last_update: str
    datasource: Optional[str]


TABULAR_LONG_TMPL = """\
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
    details = get_status_details(paths)
    if args.wait:
        while details.status in (UXAppStatus.NOT_RUN, UXAppStatus.RUNNING):
            if args.format == "tabular":
                sys.stdout.write(".")
                sys.stdout.flush()
            details = get_status_details(paths)
            sleep(0.25)
    details_dict: Dict[str, Union[None, str, List[str], Dict[str, Any]]] = {
        "datasource": details.datasource,
        "boot_status_code": details.boot_status_code.value,
        "status": details.status.value,
        "detail": details.description,
        "errors": details.errors,
        "last_update": details.last_update,
    }
    details_dict["schemas"] = {"1": copy.deepcopy(details_dict)}
    details_dict["_schema_version"] = "1"

    if args.format == "tabular":
        prefix = "\n" if args.wait else ""
        print(f"{prefix}status: {details.status.value}")
        if args.long:
            if details.last_update:
                last_update = f"last_update: {details.last_update}\n"
            else:
                last_update = ""
            print(
                TABULAR_LONG_TMPL.format(
                    prefix=prefix,
                    boot_code=details.boot_status_code.value,
                    description=details.description,
                    last_update=last_update,
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
    return 1 if details.status == UXAppStatus.ERROR else 0


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


def get_status_details(paths: Optional[Paths] = None) -> StatusDetails:
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
        status_v1 = load_json(load_file(status_file)).get("v1", {})
    latest_event = 0
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
            if finished == 0 and start != 0:
                status = UXAppStatus.RUNNING
            event_time = max(start, finished)
            if event_time > latest_event:
                latest_event = event_time
    if errors:
        status = UXAppStatus.ERROR
        description = "\n".join(errors)
    elif status == UXAppStatus.NOT_RUN and latest_event > 0:
        status = UXAppStatus.DONE
    last_update = (
        strftime("%a, %d %b %Y %H:%M:%S %z", gmtime(latest_event))
        if latest_event
        else ""
    )
    return StatusDetails(
        status, boot_status_code, description, errors, last_update, datasource
    )


def main():
    """Tool to report status of cloud-init."""
    parser = get_parser()
    sys.exit(handle_status_args("status", parser.parse_args()))


if __name__ == "__main__":
    main()
