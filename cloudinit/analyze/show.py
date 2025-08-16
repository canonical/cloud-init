#   Copyright (C) 2016 Canonical Ltd.
#
#   Author: Ryan Harper <ryan.harper@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import datetime
import json
import sys
import time
from typing import IO, Any, Dict, List, Optional, Tuple, Union

from cloudinit import subp, util
from cloudinit.distros import uses_systemd

# Example events:
#     {
#             "description": "executing late commands",
#             "event_type": "start",
#             "level": "INFO",
#             "name": "cmd-install/stage-late"
#             "origin": "cloudinit",
#             "timestamp": 1461164249.1590767,
#     }
#     {
#         "description": "executing late commands",
#         "event_type": "finish",
#         "level": "INFO",
#         "name": "cmd-install/stage-late",
#         "origin": "cloudinit",
#         "result": "SUCCESS",
#         "timestamp": 1461164249.1590767
#     }

format_key = {
    "%d": "delta",
    "%D": "description",
    "%E": "elapsed",
    "%e": "event_type",
    "%I": "indent",
    "%l": "level",
    "%n": "name",
    "%o": "origin",
    "%r": "result",
    "%t": "timestamp",
    "%T": "total_time",
}

SUCCESS_CODE = "successful"
FAIL_CODE = "failure"
CONTAINER_CODE = "container"
TIMESTAMP_UNKNOWN = (FAIL_CODE, -1, -1, -1)


def format_record(msg: str, event: Dict[str, str]) -> str:
    for i, j in format_key.items():
        if i in msg:
            # ensure consistent formatting of time values
            if j in ["delta", "elapsed", "timestamp"]:
                msg = msg.replace(i, "{%s:08.5f}" % j)
            else:
                msg = msg.replace(i, "{%s}" % j)
    return msg.format(**event)


def event_name(event: Dict[str, str]) -> Optional[str]:
    if event:
        return event.get("name")
    return None


def event_type(event: Dict[str, str]) -> Optional[str]:
    if event:
        return event.get("event_type")
    return None


def event_parent(event: Dict[str, str]) -> Optional[str]:
    name = event_name(event)
    if name:
        return name.split("/")[0]
    return None


def event_timestamp(event: Dict[str, float]) -> float:
    ts = event.get("timestamp")
    if ts is None:
        raise ValueError("Event is missing a 'timestamp'")
    return float(ts)


def event_datetime(event: Dict[str, float]) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(
        event_timestamp(event), datetime.timezone.utc
    )


def delta_seconds(t1: datetime.datetime, t2: datetime.datetime):
    return (t2 - t1).total_seconds()


def event_duration(start: Dict[str, float], finish: Dict[str, float]):
    return delta_seconds(event_datetime(start), event_datetime(finish))


def event_record(
    start_time: datetime.datetime,
    start: Dict[str, Any],
    finish: Dict[str, Any],
):
    record = finish.copy()
    name = event_name(start)
    indent = ""
    if name:
        indent = "|" + " " * (name.count("/") - 1) + "`->"
    record.update(
        {
            "delta": event_duration(start, finish),
            "elapsed": delta_seconds(start_time, event_datetime(start)),
            "indent": indent,
        }
    )

    return record


def total_time_record(total_time: float) -> str:
    return "Total Time: %3.5f seconds\n" % total_time


class SystemctlReader:
    """
    Class for dealing with all systemctl subp calls in a consistent manner.
    """

    def __init__(self, property: str, parameter: Optional[str] = None) -> None:
        self.stdout: Union[str, None] = None
        self.args: Union[str, List[str]] = ["show"]
        systemctl_path = subp.which("systemctl")
        if systemctl_path:
            self.args.append(systemctl_path)
        if parameter:
            self.args.append(parameter)
        # --timestamp=utc is needed for native date strings. Othwerise,
        # the datetime will be returned in the local timezone (which would be
        # a problem for strptime used later on in this method)
        # This option does not affect monotonic properties (values as
        # microsecond int)
        self.args.extend(["-p", property, "--timestamp=us+utc"])

        # Don't want the init of our object to break. Instead of throwing
        # an exception, set an error code that gets checked when data is
        # requested from the object
        self.failure = self.subp()

    def subp(self) -> Optional[Union[str, Exception]]:
        """
        Make a subp call based on set args and handle errors by setting
        failure code

        :return: whether the subp call failed or not
        """
        try:
            value, err = subp.subp(self.args, capture=True)
            if err:
                return err
            self.stdout = value
            return None
        except Exception as systemctl_fail:
            return systemctl_fail

    def convert_val_to_float(self) -> float:
        """
        If subp call succeeded, return the timestamp from subp as a float.

        :return: timestamp as a float
        """
        # subp has 2 ways to fail: it either fails and throws an exception,
        # or returns an error code. Raise an exception here in order to make
        # sure both scenarios throw exceptions
        if self.failure:
            raise RuntimeError(
                "Subprocess call to systemctl has failed, "
                "returning error code ({})".format(self.failure)
            )
        # Output from systemctl show has the format Property=Value.

        if self.stdout is None:
            raise RuntimeError("SystemctlReader.stdout is None")

        val = self.stdout.split("=")[1].strip()

        if val.isnumeric():
            # Float Timestamps reported by systemctl are in
            # microseconds, converting to seconds
            # For example, UserspaceMonotonic=1929304
            timestamp = float(val) / 1000000
        else:
            # The format in this case is always "%a %Y-%m-%d %H:%M:%S %Z"
            # For example, UserspaceTimestamp=Wed 2025-07-30 05:14:32 UTC

            # strptime returns a naive datetime so we need to explictly
            # set the timezone of this datetime
            # at the timezone of the parsed string (utc)
            timestamp = (
                datetime.datetime.strptime(val, "%a %Y-%m-%d %H:%M:%S.%f %Z")
                .replace(tzinfo=datetime.timezone.utc)
                .timestamp()
            )

        return timestamp


def dist_check_timestamp() -> Tuple[str, float, float, float]:
    """
    Determine which init system a particular linux distro is using.
    Each init system (systemd, etc) has a different way of
    providing timestamps.

    :return: timestamps of kernelboot, kernelendboot, and cloud-initstart
    or TIMESTAMP_UNKNOWN if the timestamps cannot be retrieved.
    """

    if uses_systemd():
        return gather_timestamps_using_systemd()

    # Use dmesg to get timestamps if the distro does not have systemd
    if util.is_FreeBSD() or "gentoo" in util.system_info()["system"].lower():
        return gather_timestamps_using_dmesg()

    # this distro doesn't fit anything that is supported by cloud-init. just
    # return error codes
    return TIMESTAMP_UNKNOWN


def gather_timestamps_using_dmesg() -> Tuple[str, float, float, float]:
    """
    Gather timestamps that corresponds to kernel begin initialization,
    kernel finish initialization using dmesg as opposed to systemctl

    :return: the two timestamps plus a dummy timestamp to keep consistency
    with gather_timestamps_using_systemd
    """
    try:
        data, _ = subp.subp(["dmesg"], capture=True)
        split_entries = data[0].splitlines()
        for i in split_entries:
            if i.decode("UTF-8").find("user") != -1:
                splitup = i.decode("UTF-8").split()
                stripped = splitup[1].strip("]")

                # kernel timestamp from dmesg is equal to 0,
                # with the userspace timestamp relative to it.
                user_space_timestamp = float(stripped)
                kernel_start = float(time.time()) - float(util.uptime())
                kernel_end = kernel_start + user_space_timestamp

                # systemd wont start cloud-init in this case,
                # so we cannot get that timestamp
                return SUCCESS_CODE, kernel_start, kernel_end, kernel_end

    except Exception:
        pass
    return TIMESTAMP_UNKNOWN


def gather_timestamps_using_systemd() -> Tuple[str, float, float, float]:
    """
    Gather timestamps that corresponds to kernel begin initialization,
    kernel finish initialization. and cloud-init systemd unit activation

    :return: the three timesread_propertystamps
    """
    try:
        # The use of the monotonic timestamps is needed in cloud-init-related
        # dates to account for the 2-second delay when cloud-init sets up NTP
        if util.is_container():
            # lxc based containers do not set their monotonic zero point to be
            # when the container starts,
            # instead keep using host boot as zero point
            kernel_start = SystemctlReader(
                "UserspaceTimestamp"
            ).convert_val_to_float()
            monotonic_offset = SystemctlReader(
                "UserspaceTimestampMonotonic"
            ).convert_val_to_float()
        else:
            kernel_start = SystemctlReader(
                "KernelTimestamp"
            ).convert_val_to_float()
            monotonic_offset = SystemctlReader(
                "KernelTimestampMonotonic"
            ).convert_val_to_float()
        kernel_end = (
            SystemctlReader(
                "UserspaceTimestampMonotonic"
            ).convert_val_to_float()
            - monotonic_offset
        )
        cloudinit_sysd = (
            SystemctlReader(
                "InactiveExitTimestampMonotonic", "cloud-init-local"
            ).convert_val_to_float()
            - monotonic_offset
        )

    except Exception as e:
        # Except ALL exceptions as Systemctl reader can throw many different
        # errors, but any failure in systemctl means that timestamps cannot be
        # obtained
        print(e)
        return TIMESTAMP_UNKNOWN

    status = CONTAINER_CODE if util.is_container() else SUCCESS_CODE

    return (
        status,
        kernel_start,
        kernel_start + kernel_end,
        kernel_start + cloudinit_sysd,
    )


def generate_records(
    events: List[Dict[str, Any]],
    print_format: str = "(%n) %d seconds in %I%D",
) -> List[List[str]]:
    """
    Take in raw events and create parent-child dependencies between events
    in order to order events in chronological order.

    :param events: JSONs from dump that represents events taken from logs
    :param print_format: formatting to represent event, time stamp,
    and time taken by the event in one line

    :return: boot records ordered chronologically
    """

    sorted_events = sorted(events, key=lambda x: x["timestamp"])
    records: List[str] = []
    start_time = None
    total_time = 0.0
    stage_start_time = {}
    boot_records = []

    unprocessed = []
    for e in range(len(sorted_events)):
        event = events[e]
        try:
            next_evt = events[e + 1]
        except IndexError:
            next_evt = None

        if event_type(event) == "start":
            if records and event.get("name") == "init-local":
                records.append(total_time_record(total_time))
                boot_records.append(records)
                records = []
                start_time = None
                total_time = 0.0

            if start_time is None:
                start_time = event_datetime(event)
                stage_start_time[event_parent(event)] = start_time

            # see if we have a pair
            if next_evt is not None:
                if event_name(event) == event_name(next_evt):
                    if event_type(next_evt) == "finish":
                        records.append(
                            format_record(
                                print_format,
                                event_record(start_time, event, next_evt),
                            )
                        )
                else:
                    # This is a parent event
                    records.append("Starting stage: %s" % event.get("name"))
                    unprocessed.append(event)
                    continue
        else:
            prev_evt = unprocessed.pop()
            if prev_evt is not None:
                if event_name(event) == event_name(prev_evt):
                    if start_time:
                        record = event_record(start_time, prev_evt, event)
                        records.append(
                            format_record(
                                "Finished stage: (%n) %d seconds", record
                            )
                            + "\n"
                        )
                        total_time += record.get("delta")
                else:
                    # not a match, put it back
                    unprocessed.append(prev_evt)

    records.append(total_time_record(total_time))
    boot_records.append(records)
    return boot_records


def show_events(
    events: List[Dict[str, Any]], print_format: str
) -> List[List[str]]:
    """
    A passthrough method that makes it easier to call generate_records()

    :param events: JSONs from dump that represents events taken from logs
    :param print_format: formatting to represent event, time stamp,
    and time taken by the event in one line

    :return: boot records ordered chronologically
    """
    return generate_records(events, print_format=print_format)


def load_events_infile(
    infile: IO,
) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Takes in a log file, read it, and convert to json.

    :param infile: The Log file to be read

    :return: json version of logfile, raw file
    """
    data = infile.read()
    if not data.strip():
        sys.stderr.write("Empty file %s\n" % infile.name)
        sys.exit(1)
    try:
        return json.loads(data), data
    except ValueError:
        return None, data
