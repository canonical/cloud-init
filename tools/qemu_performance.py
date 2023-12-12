#!/usr/bin/env python3
"""Basic local performance bootspeed testing using QEMU

Boot a control image in QEMU for certain number of sample boots and
extract bootspeed-related samples and logs via commands or logs such as:
 - systemd-analyze, systemd-analyze critical-chain, cloud-init analyze
 - journalctl, /var/log/cloud-init.log.

Create a derivative image with cloud-init upgraded in QEMU which has not yet
booted. Cloud-init can be installed either from a local deb or by providing
ppa:<custom_ppa>.

Launch multiple instances up to --number-of-launches of control and upgraded
cloudimages.

Persist all metrics artifacts in --data-dir as JSON files.
Calculate averages across all control runs and upgraded image samples.

Highlight deltas between control verus upgraded averages which
are greater than 0.1 seconds different and 20 percent different.


REQUIREMENTS:
- sudo permissions to mount ISO images
- mount-image-callback utility from cloud-image-utils deb package
"""

import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from argparse import ArgumentParser, FileType
from copy import deepcopy
from pathlib import Path

import pycloudlib

# Number of original and upgraded boots to perform and evaluate
BOOT_SAMPLES = 3

# Do not report performance deltas where average delta for service between
# control and new images is less than this number of seconds
MIN_AVG_DELTA = 0.1

# Do not report performance deltas for services where average delta between
# control and new is below this percentage
MIN_AVG_PERCENT_DELTA = 20


MANDATORY_REPORT_KEYS = ("time_cloudinit_total", "time_systemd_userspace", "client_time_to_ssh")

DEFAULT_PPA = "ppa:cloud-init-dev/daily"


def retry_cmd(instance, cmd):
    for retry_sleep in [0.25] * 400:
        try:
            return instance.execute(cmd)
        except Exception:
            time.sleep(retry_sleep)


def update_cloud_init_in_img(img_path: str, deb_path: str, suffix=".modified"):
    """Use mount-image-callback to install a known deb into an image"""
    new_img_path = os.path.basename(img_path.replace(".img", f".img{suffix}"))
    new_img_path = f"{os.getcwd()}/{new_img_path}"
    shutil.copy(img_path, new_img_path)
    subprocess.check_call(["sync"])
    if deb_path.endswith(".deb"):
        commands = [
            [
                "sudo",
                "mount-image-callback",
                "--system-mounts", "--system-resolvconf",
                new_img_path,
                "--",
                "sh",
                "-c",
                f"chroot ${{MOUNTPOINT}} apt-get update; DEBIAN_FRONTEND=noninteractive chroot ${{MOUNTPOINT}} apt-get install -o  Dpkg::Options::='--force-confold' dhcpcd5 -y --force-yes",
            ],
            [
                "sudo",
                "mount-image-callback",
                new_img_path,
                "--",
                "sh",
                "-c",
                f"cp {deb_path} ${{MOUNTPOINT}}/.; chroot ${{MOUNTPOINT}} dpkg -i /{os.path.basename(deb_path)}",
            ],
        ]
    elif deb_path.startswith("ppa:"):
        commands = [
            [
                "sudo",
                "mount-image-callback",
                "--system-mounts", "--system-resolvconf",
                new_img_path,
                "--",
                "sh",
                "-c",
                f"chroot ${{MOUNTPOINT}} add-apt-repository {deb_path} -y; DEBIAN_FRONTEND=noninteractive chroot ${{MOUNTPOINT}} apt-get install -o  Dpkg::Options::='--force-confold' cloud-init -y",
            ],
        ]
    else:
        raise RuntimeError(
            f"Invalid deb_path provided: {deb_path}. Expected local .deb or" " ppa:"
        )
    for command in commands:
        logging.debug(f"--- Running: {' '.join(command)}")
        subprocess.check_call(command)
    return new_img_path


def collect_bootspeed_data(instance):
    """Collect and process bootspeed data from the instance."""
    start_time = time.time()
    data = {"time_at_ssh": retry_cmd(instance, "date --utc +'%b %d %H:%M:%S.%N'")}
    ssh_time = time.time()
    data["cloudinit_status"] = json.loads(
        instance.execute("cloud-init status --format=json --wait")
    )
    cloudinit_done_time = time.time()
    data["client_time_to_ssh"] = ssh_time - start_time
    data["client_time_to_cloudinit_done"] = cloudinit_done_time - start_time
    data["image_builddate"] = retry_cmd(
        instance, "grep serial /etc/cloud/build.info"
    ).split()[-1]
    data["systemd_analyze"] = retry_cmd(instance, "systemd-analyze")
    data["systemd_analyze_blame"] = retry_cmd(instance, "systemd-analyze blame")
    data["cloudinit_version"]: retry_cmd(instance, "dpkg-query -W cloud-init").split()[
        1
    ]
    data["cloudinit_analyze"] = instance.execute("cloud-init analyze show")
    data["cloudinit_analyze_blame"] = instance.execute("cloud-init analyze blame")

    for service in (
        "cloud-init.service",
        "cloud-init-local.sevice",
        "cloud-config.service",
        "cloud-final.service",
        "systemd-user-sessions.service",  # Affects sytem login time
        "snapd.seeded.service",  # Has impact on cloud-config.service
    ):
        data[
            f"criticalchain_{service.replace('-', '_').replace('.', '_')}"
        ] = instance.execute(f"systemd-analyze critical-chain {service}")
    data["file_journalctl.log"] = instance.execute(
        "journalctl -o short-precise"
    )
    data["file_cloud_init.log"] = instance.execute(
        "cat /var/log/cloud-init.log"
    )
    return data


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
    analyze_times = re.match(
        r".*in.* ((?P<firmware>[^s]+)s \(firmware\) \+ (?P<loader>[^s]+)s \(loader\) \+ )?(?P<kernel>[^s]+)s \(kernel\) \+ (?P<user>[^s]+)s \(userspace\)",
        boot_sample["systemd_analyze"],
    )
    if analyze_times:
        boot_sample["time_systemd_kernel"] = float(analyze_times["kernel"])
        boot_sample["time_systemd_userspace"] = float(analyze_times["user"])
    systemd_blames = {}
    for line in boot_sample["systemd_analyze_blame"].splitlines():
        blame = re.match(r"\s*(?P<cost>[\d.]+)s (?P<service_name>\S+)", line)
        if blame:
            systemd_blames[blame["service_name"]] = float(blame["cost"])
    boot_sample["time_systemd_blames"] = systemd_blames

    # Process cloud-init analyze blame output for each config module cost
    cloudinit_blames = {}
    for line in boot_sample["cloudinit_analyze_blame"].splitlines():
        blame = re.match(r"(?P<cost>[^s]+)s \((?P<module_name>[^\)]+)\)", line.strip())
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
    re.DOTALL)
    if stage_total_time:
        boot_sample["time_cloudinit_total"] = float(stage_total_time["cost"])
    boot_sample["time_cloudinit_blames"] = cloudinit_blames


def update_averages(boot_samples: list[dict], data_dir: Path, data_type: str):
    avg_data = {
        "client_time_to_ssh": {"samples": []},
        "client_time_to_cloudinit_done": {"samples": []},
        "time_systemd_kernel": {"samples": []},
        "time_systemd_userspace": {"samples": []},
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
    for idx, boot_sample in enumerate(boot_samples):
        for file_key in  [k for k in boot_sample.keys() if k.startswith('file_')]:
            data_file = data_dir / f"{data_type}-instance-{idx}-{file_key[5:]}"
            data_file.write_text(boot_sample.pop(file_key))
        artifacts_file = data_dir / f"{data_type}-instance-{idx}-artifacts.json"
        artifacts_file.write_text(json.dumps(boot_sample, indent=1, sort_keys=True))
    avg_file = data_dir / f"{data_type}-avg.json"
    avg_file.write_text(json.dumps(avg_data, indent=1, sort_keys=True))
    return avg_data


HEADER = """\
------------------- Boot speed comparison ---------------------------
Boot image serial: {boot_serial}
Cloud-init from: {deb_path}
Source image: {source_image}
Number of samples: {sample_count}
Min time delta percentage considered significant: {min_avg_delta}%
---------------------------------------------------------------------

"""

METRIC_TABLE_HEADER = """\
------------------- {image_name:>18} image --------------------------
| Avg/Stdev     |   Max   |  Min    | Metric Name
-----------------------------------------------------------------------"""

METRIC_LINE = """| {avg:06.2f}s/{stdev:04.2f}s | {max:06.2f}s | {min:06.2f}s | {name}"""


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
            perf_delta = report_significant_avg_delta(key, orig_avg[key], new_avg[key])
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


def inspect_boot_time_deltas_for_deb(
    deb_path: str,
    sample_count: int,
    release: str,
    data_dir: Path,
    user_data: str,
):
    """
    Download daily image for a given release.
    Boot that daily image and inspect typical data related
    to boottime:
     1. systemd-analyze blame:
        - to see costs of cloud-init units vs snapd.seeded.service
     2. systemd-analyze critical-chain systemd-user-sessions.service
        - generally blocks console login and non-root SSH access to VM
     3. systemd-analyze critical-chain cloud-config.service
        - which typically blocks on a costly snapd.seeded.service for this VM
     4. systemd-analyze critical-chain snapd.seeded.service:
        - to ensure we are seeding snaps during this boot and didn't use a
          dirty image which already seeded
     5. cloud-init analyze blame: To highlight where time is spent.
        Particular attention to cc_apt_configure additional time cost
     6. grep update /var/log/cloud-init.log to assert whether apt-get update
        is called in default cases.

    Use mount-image-callback to inject deb_path into a derivative daily image.
    Boot original daily image and report boottime stats.
    Boot derivative image and report boottime stats.
    """
    orig_data = []
    new_data = []
    existing_data_files = [f for f in data_dir.rglob("*.json")]
    if existing_data_files:
        print(f"--- Using pre-existing data files in {data_dir}")
        daily = "pre-existing samples"
        for f in existing_data_files:
            if "avg" in f.name:
                continue
            if "orig" in f.name:
                orig_data.append(json.loads(f.read_text()))
            else:
                new_data.append(json.loads(f.read_text()))
    else:
        data_dir.mkdir(exist_ok=True)
        with pycloudlib.Qemu(tag="examples") as cloud:
            daily = cloud.daily_image(release=release)
            print(
                f"--- Creating modified daily image {daily} with cloud-init"
                f" from {deb_path}"
            )
            new_image = update_cloud_init_in_img(daily, deb_path, suffix=1)
            print(
                f"--- Launching {sample_count} control daily images {daily} ---"
            )
            for sample in range(sample_count):
                instance = cloud.launch(image_id=daily, user_data=user_data)
                orig_data.append(collect_bootspeed_data(instance))
                instance.delete()
                new_instance = cloud.launch(image_id=new_image, user_data=user_data)
                new_data.append(collect_bootspeed_data(new_instance))
                new_instance.delete()
    orig_avg = update_averages(orig_data, data_dir, "orig")
    new_avg = update_averages(new_data, data_dir, "new")
    print(
        HEADER.format(
            boot_serial=orig_data[0]["image_builddate"],
            deb_path=deb_path,
            source_image=str(daily),
            sample_count=sample_count,
            min_avg_delta=MIN_AVG_PERCENT_DELTA,
        )
    )
    report_errors(new_data)
    inspect_averages(orig_avg, new_avg)


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
        if status["errors"] or status["recoverable_errors"]:
            print(CLOUDINIT_ERRORS.format(idx=idx, **status))


def get_parser():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--number-of-launches",
        dest="sample_count",
        type=int,
        default=BOOT_SAMPLES,
        help="Number of image samples to launch",
    )
    parser.add_argument(
        "-u",
        "--user-data",
        dest="user_data",
        type=FileType("r"),
        default=None,
        help="Optional user-data to send to the instances launched",
    )
    parser.add_argument(
        "-r",
        "--release",
        default="noble",
        choices=["focal", "jammy", "lunar", "mantic", "noble", "oracular"],
        help="Ubuntu series to test",
    )
    parser.add_argument(
        "-d",
        "--data-dir",
        dest="data_dir",
        default="perf_data",
        help=(
            "Data directory in which to store perf value dicts." f" Default: perf_data"
        ),
    )
    parser.add_argument(
        "-c",
        "--cloud-init-source-path",
        default=DEFAULT_PPA,
        dest="deb_path",
        help=(
            "Deb path or PPA from which to install cloud-init for testing."
            f" Default {DEFAULT_PPA}"
        ),
    )
    return parser

def assert_dependencies():
    """Fail on any missing dependencies."""
    if not shutil.which("mount-image-callback"):
        raise RuntimeError(
            "Missing mount-image-callback utility. "
            "Try: apt-get install cloud-image-utils"
        )


if __name__ == "__main__":
    assert_dependencies()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("qemu.qmp.protocol").setLevel(logging.WARNING)
    logging.getLogger("pycloudlib").setLevel(logging.INFO)
    logging.getLogger("paramiko.transport:Auth").setLevel(logging.INFO)
    parser = get_parser()
    args = parser.parse_args()
    user_data = args.user_data.read() if args.user_data else None
    inspect_boot_time_deltas_for_deb(
        args.deb_path,
        sample_count=args.sample_count,
        release=args.release,
        data_dir=Path(args.data_dir),
        user_data=user_data,
    )
