# Copyright (C) 2017 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Define 'status' utility and handler as part of cloud-init commandline."""

import argparse
import enum
import os
import sys
from time import gmtime, sleep, strftime

from cloudinit.distros import uses_systemd
from cloudinit.stages import Init
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


def handle_status_args(name, args):
    """Handle calls to 'cloud-init status' as a subcommand."""
    # Read configured paths
    init = Init(ds_deps=[])
    init.read_cfg()
    status, status_detail, time = get_status_details(init.paths)
    if args.wait:
        while status in (UXAppStatus.NOT_RUN, UXAppStatus.RUNNING):
            sys.stdout.write(".")
            sys.stdout.flush()
            status, status_detail, time = get_status_details(init.paths)
            sleep(0.25)
        sys.stdout.write("\n")
    print("status: {0}".format(status.value))
    if args.long:
        if time:
            print("time: {0}".format(time))
        print("detail:\n{0}".format(status_detail))
    return 1 if status == UXAppStatus.ERROR else 0


def _is_cloudinit_disabled(disable_file, paths):
    """Report whether cloud-init is disabled.

    @param disable_file: The path to the cloud-init disable file.
    @param paths: An initialized cloudinit.helpers.Paths object.
    @returns: A tuple containing (bool, reason) about cloud-init's status and
    why.
    """
    is_disabled = False
    cmdline_parts = get_cmdline().split()
    if not uses_systemd():
        reason = "Cloud-init enabled on sysvinit"
    elif "cloud-init=enabled" in cmdline_parts:
        reason = "Cloud-init enabled by kernel command line cloud-init=enabled"
    elif os.path.exists(disable_file):
        is_disabled = True
        reason = "Cloud-init disabled by {0}".format(disable_file)
    elif "cloud-init=disabled" in cmdline_parts:
        is_disabled = True
        reason = "Cloud-init disabled by kernel parameter cloud-init=disabled"
    elif os.path.exists(os.path.join(paths.run_dir, "disabled")):
        is_disabled = True
        reason = "Cloud-init disabled by cloud-init-generator"
    elif os.path.exists(os.path.join(paths.run_dir, "enabled")):
        reason = "Cloud-init enabled by systemd cloud-init-generator"
    else:
        reason = "Systemd generator may not have run yet."
    return (is_disabled, reason)


def get_status_details(paths=None):
    """Return a 3-tuple of status, status_details and time of last event.

    @param paths: An initialized cloudinit.helpers.paths object.

    Values are obtained from parsing paths.run_dir/status.json.
    """
    if not paths:
        init = Init(ds_deps=[])
        init.read_cfg()
        paths = init.paths

    status = UXAppStatus.NOT_RUN
    status_detail = ""
    status_v1 = {}

    status_file = os.path.join(paths.run_dir, "status.json")
    result_file = os.path.join(paths.run_dir, "result.json")

    (is_disabled, reason) = _is_cloudinit_disabled(
        CLOUDINIT_DISABLED_FILE, paths
    )
    if is_disabled:
        status = UXAppStatus.DISABLED
        status_detail = reason
    if os.path.exists(status_file):
        if not os.path.exists(result_file):
            status = UXAppStatus.RUNNING
        status_v1 = load_json(load_file(status_file)).get("v1", {})
    errors = []
    latest_event = 0
    for key, value in sorted(status_v1.items()):
        if key == "stage":
            if value:
                status = UXAppStatus.RUNNING
                status_detail = "Running in stage: {0}".format(value)
        elif key == "datasource":
            status_detail = value
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
        status_detail = "\n".join(errors)
    elif status == UXAppStatus.NOT_RUN and latest_event > 0:
        status = UXAppStatus.DONE
    if latest_event:
        time = strftime("%a, %d %b %Y %H:%M:%S %z", gmtime(latest_event))
    else:
        time = ""
    return status, status_detail, time


def main():
    """Tool to report status of cloud-init."""
    parser = get_parser()
    sys.exit(handle_status_args("status", parser.parse_args()))


if __name__ == "__main__":
    main()

# vi: ts=4 expandtab
