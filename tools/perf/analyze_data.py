#!/usr/bin/env python3
"""
Calculate averages across all control runs and upgraded image samples.

Highlight deltas between control verus upgraded averages which
are greater than 0.1 seconds different and 20 percent different.
"""

# ruff: noqa: E501

import json
import logging
import re
import statistics
from argparse import ArgumentParser
from pathlib import Path

# Do not report performance deltas where average delta for service between
# control and new images is less than this number of seconds
MIN_AVG_DELTA = 0.1

# Do not report performance deltas for services where average delta between
# control and new is below this percentage
MIN_AVG_PERCENT_DELTA = 20


MANDATORY_REPORT_KEYS = (
    "time_cloudinit_total",
    "client_time_to_ssh",
)


def get_max_min_avg(samples: list):
    return {
        "max": max(samples),
        "min": min(samples),
        "avg": float(sum(samples) / len(samples)),
        "stdev": 0.0 if len(samples) < 2 else statistics.stdev(samples),
    }


def process_bootspeed_data(boot_sample: dict):
    """Process semi-structured boot_sample, extracting boot times

    Process systemd-analyze blame and cloud-init analyze blame output
    to create top-level keys and associated boot time cost in seconds
    for the following boot data:
       time_systemd_kernel, time_systemd_userspace,
       time_systemd_blames (dict of services and costs) and
       time_cloudnit_blames (dict of config modules, boot stages).
    """
    systemd_blames = {}
    for line in boot_sample["systemd_analyze_blame"].splitlines():
        blame = re.match(r"\s*(?P<cost>[\d.]+)s (?P<service_name>\S+)", line)
        if blame:
            systemd_blames[blame["service_name"]] = float(blame["cost"])
    boot_sample["time_systemd_blames"] = systemd_blames

    # Process cloud-init analyze blame output for each config module cost
    cloudinit_blames = {}
    for line in boot_sample["cloudinit_analyze_blame"].splitlines():
        blame = re.match(
            r"(?P<cost>[^s]+)s \((?P<module_name>[^\)]+)\)", line.strip()
        )
        if blame:
            cloudinit_blames[blame["module_name"]] = float(blame["cost"])

    # Process cloud-init analyze show output for each boot stage cost
    for match in re.findall(
        r"Finished stage: \((?P<stage>[^)]+)\) (?P<cost>[\d.]+) seconds",
        boot_sample["cloudinit_analyze"],
    ):
        cloudinit_blames[f"stage/{match[0]}"] = float(match[1])
    stage_total_time = re.match(
        r".*\nTotal Time: (?P<cost>[\d\.]+) seconds\n",
        boot_sample["cloudinit_analyze"],
        re.DOTALL,
    )
    if stage_total_time:
        boot_sample["time_cloudinit_total"] = float(stage_total_time["cost"])
    boot_sample["time_cloudinit_blames"] = cloudinit_blames


def update_averages(boot_samples: list[dict], data_dir: Path, data_type: str):
    avg_data: dict[str, dict] = {
        "client_time_to_ssh": {"samples": []},
        "client_time_to_cloudinit_done": {"samples": []},
        "time_cloudinit_total": {"samples": []},
        "time_systemd_blames": {},
        "time_cloudinit_blames": {},
    }
    for boot_sample in boot_samples:
        process_bootspeed_data(boot_sample)
        for k in avg_data:
            if "blames" in k:
                for service_name in boot_sample[k]:
                    if service_name not in avg_data[k]:
                        avg_data[k][service_name] = {
                            "samples": [boot_sample[k][service_name]]
                        }
                    else:
                        avg_data[k][service_name]["samples"].append(
                            boot_sample[k][service_name]
                        )
            else:
                avg_data[k]["samples"].append(boot_sample[k])

    for k in avg_data:
        if "blames" in k:
            for service_name in avg_data[k]:
                avg_data[k][service_name].update(
                    get_max_min_avg(avg_data[k][service_name]["samples"])
                )
        else:
            avg_data[k].update(get_max_min_avg(avg_data[k]["samples"]))
    avg_file = data_dir / f"{data_type}-avg.json"
    avg_file.write_text(json.dumps(avg_data, indent=1, sort_keys=True))
    return avg_data


HEADER = """\
------------------- Boot speed comparison ---------------------------
Boot image serial: {boot_serial}
Min time delta percentage considered significant: {min_avg_delta}%
---------------------------------------------------------------------

"""

METRIC_TABLE_HEADER = """\
------------------- {image_name:>18} image --------------------------
| Avg/Stdev     |   Max   |  Min    | Metric Name
-----------------------------------------------------------------------"""

METRIC_LINE = (
    """| {avg:06.2f}s/{stdev:04.2f}s | {max:06.2f}s | {min:06.2f}s | {name}"""
)


def log_avg_table(image_name, avg):
    avg_table_content = METRIC_TABLE_HEADER.format(image_name=image_name)
    for key in avg:
        if "blame" in key:
            for service in avg[key]:
                if avg[key][service]["avg"] > MIN_AVG_DELTA:
                    avg_table_content += "\n" + METRIC_LINE.format(
                        name=service,
                        avg=avg[key][service]["avg"],
                        max=avg[key][service]["max"],
                        min=avg[key][service]["min"],
                        stdev=avg[key][service]["stdev"],
                    )
        elif avg[key]["avg"] > MIN_AVG_DELTA:
            avg_table_content += "\n" + METRIC_LINE.format(
                name=key,
                avg=avg[key]["avg"],
                max=avg[key]["max"],
                min=avg[key]["min"],
                stdev=avg[key]["stdev"],
            )
    print(avg_table_content)


PERF_HEADER = """\
--------------------- Performance Deltas Encountered ---------------------------------
| Control Avg/Stdev |  Upgr. Avg/Stdev | Avg delta | Delta type and service name
--------------------------------------------------------------------------------------"""

PERF_LINE = """\
|     {orig_avg:06.2f}s/{orig_stdev:04.2f}s |    {new_avg:06.2f}s/{new_stdev:04.2f}s |   {avg_delta:+06.2f}s | ***{delta_type} {name:<24}"""


def report_significant_avg_delta(key, orig_sample, new_sample):
    """Return dict describing service boottime deltas when significant.

    Compare orig_sample to new_sample average boottimes. If the percentage
    delta between orig and new are significant, return a string classifying
    whether the delta is IMPROVED or DEGRADED in comparison to the orig_sample.

    :return: Empty dict when no significant delta present. Otherwise, a
        dict containing significant delta characteristics:
           name, orig_avg, new_avg,
        DEGRADED boottimes for this comparison. Return empty string if no
        significant difference exists.
    """
    avg_delta_time = new_sample["avg"] - orig_sample["avg"]
    if orig_sample["avg"] > 0:
        avg_delta_pct = new_sample["avg"] / orig_sample["avg"] * 100 - 100
    else:
        avg_delta_pct = 100
    if abs(avg_delta_time) < MIN_AVG_DELTA:
        if key not in MANDATORY_REPORT_KEYS:
            # Always want to print the above keys
            return {}
    if abs(avg_delta_pct) < MIN_AVG_PERCENT_DELTA:
        if key not in MANDATORY_REPORT_KEYS:
            # Always want to print the above keys
            return {}
    if abs(avg_delta_pct) < MIN_AVG_PERCENT_DELTA and abs(avg_delta_time) < 2:
        delta_type = "        "
    elif avg_delta_pct > 0:
        delta_type = "DEGRADED"
    else:
        delta_type = "IMPROVED"
    return {
        "orig_avg": orig_sample["avg"],
        "orig_stdev": orig_sample["stdev"],
        "new_avg": new_sample["avg"],
        "new_stdev": new_sample["stdev"],
        "avg_delta": new_sample["avg"] - orig_sample["avg"],
        "name": key,
        "delta_type": delta_type,
    }


def inspect_averages(orig_avg, new_avg):
    perf_deltas = []

    for key in orig_avg:
        if "avg" in orig_avg[key] and orig_avg[key]["avg"] > MIN_AVG_DELTA:
            perf_delta = report_significant_avg_delta(
                key, orig_avg[key], new_avg[key]
            )
            if perf_delta:
                perf_deltas.append(PERF_LINE.format(**perf_delta))
        else:
            for service in set(orig_avg[key].keys()).union(new_avg.keys()):
                if service in orig_avg[key] and service in new_avg[key]:
                    perf_delta = report_significant_avg_delta(
                        service, orig_avg[key][service], new_avg[key][service]
                    )
                    if perf_delta:
                        perf_deltas.append(PERF_LINE.format(**perf_delta))
    if perf_deltas:
        perf_deltas.insert(0, PERF_HEADER)
    for delta in perf_deltas:
        print(delta)
    if not perf_deltas:
        print("------ No significant boot speed deltas seen -----")
    log_avg_table("Control", orig_avg)
    log_avg_table("Updated cloud-init", new_avg)


def analyze_data(data_dir: Path):
    """analyze data in directory"""
    orig_data = json.loads((Path(data_dir) / "orig.json").read_text())
    orig_avg = update_averages(orig_data, data_dir, "orig")
    print(
        HEADER.format(
            boot_serial=orig_data[0]["image_builddate"],
            min_avg_delta=MIN_AVG_PERCENT_DELTA,
        )
    )
    report_errors(orig_data)
    log_avg_table("Image cloud-init", orig_avg)


CLOUDINIT_ERRORS = """\
------------ Unexpected errors  ---------------------------------------
Sample name: new-instance-{idx}-artifacts.json
Errors:
{errors}
Recoverable Errors:
{recoverable_errors}
-----------------------------------------------------------------------
"""


def report_errors(samples: list):
    """Print any unexpected errors found data samples"""
    for idx, sample in enumerate(samples):
        status = sample["cloudinit_status"]
        if status["errors"] or status.get("recoverable_errors"):
            print(CLOUDINIT_ERRORS.format(idx=idx, **status))


def get_parser():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        dest="data_dir",
        default="perf_data",
        help=(
            "Data directory in which to store perf value dicts."
            "Default: perf_data"
        ),
    )
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("qemu.qmp.protocol").setLevel(logging.WARNING)
    logging.getLogger("pycloudlib").setLevel(logging.INFO)
    logging.getLogger("paramiko.transport:Auth").setLevel(logging.INFO)
    parser = get_parser()
    args = parser.parse_args()
    analyze_data(
        data_dir=Path(args.data_dir),
    )
