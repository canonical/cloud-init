#!/usr/bin/env python3
"""Basic local performance bootspeed testing

Launch --number-of-launches instances. Extract bootspeed samples such as:
 - systemd-analyze, systemd-analyze critical-chain, cloud-init analyze
 - journalctl, /var/log/cloud-init.log.

Persist all metrics artifacts in a JSON file, print the data directory to stdout
"""

# ruff: noqa: E501

import json
import logging
import time
from argparse import ArgumentParser, FileType
from pathlib import Path
from tempfile import TemporaryDirectory


import pycloudlib

PLATFORM_FROM_STR = {
    "qemu": pycloudlib.Qemu,
    "gce": pycloudlib.GCE,
    "ec2": pycloudlib.EC2,
    "lxd_container": pycloudlib.LXDContainer,
    "lxd_vm": pycloudlib.LXDVirtualMachine,
}

MANDATORY_REPORT_KEYS = (
    "time_cloudinit_total",
    "client_time_to_ssh",
)


def retry_cmd(instance, cmd):
    while True:
        try:
            return instance.execute(cmd)
        except Exception:
            time.sleep(0.01)


def collect_bootspeed_data(results_dir, cloud, image_id, user_data):
    """Collect and process bootspeed data from the instance."""
    start_time = time.time()
    instance = cloud.launch(image_id=image_id, user_data=user_data)
    data = {
        "time_at_ssh": retry_cmd(instance, "date --utc +'%b %d %H:%M:%S.%N'")
    }
    ssh_time = time.time()
    instance.execute("cloud-init status --wait")
    try:
        data["cloudinit_status"] = json.loads(
            instance.execute("cloud-init status --format=json")
        )
    except json.decoder.JSONDecodeError:
        # doesn't work on xenial
        data["cloudinit_status"] = ""
    cloudinit_done_time = time.time()
    data["client_time_to_ssh"] = ssh_time - start_time
    data["client_time_to_cloudinit_done"] = cloudinit_done_time - start_time
    data["image_builddate"] = retry_cmd(
        instance, "grep serial /etc/cloud/build.info"
    ).split()[-1]
    data["systemd_analyze_blame"] = retry_cmd(
        instance, "systemd-analyze blame"
    )
    data["cloudinit_version"] = retry_cmd(
        instance, "dpkg-query -W cloud-init"
    ).split()[1]
    data["cloudinit_analyze"] = instance.execute("cloud-init analyze show")
    data["cloudinit_analyze_blame"] = instance.execute(
        "cloud-init analyze blame"
    )

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
    instance.delete()
    return data


def launch_instances(
    results_dir: str,
    sample_count: int,
    image: str,
    platform: str,
    user_data: str,
):
    """
    Boot the image and inspect typical data related to boottime.

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
    """
    orig_data = []
    with PLATFORM_FROM_STR[platform](tag="examples") as cloud:
        print(f"--- Launching {sample_count} daily images {image} ---")
        for sample in range(sample_count):
            print(f"--- Launching instance #{1 + sample} ---")
            orig_data.append(
                collect_bootspeed_data(
                    results_dir,
                    cloud=cloud,
                    image_id=image,
                    user_data=user_data,
                )
            )
    print("--- Saving results ---")
    write_data(results_dir, orig_data)


def write_data(results_dir: str, boot_samples, data_type="orig"):
    """Write sampled outputs, return the destination directory"""
    avg_file = Path(results_dir) / f"{data_type}.json"
    avg_file.write_text(json.dumps(boot_samples, indent=1, sort_keys=True))
    return


def get_parser():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--number-of-launches",
        required=True,
        dest="sample_count",
        type=int,
        help="Number of image samples to launch",
    )
    parser.add_argument(
        "--platform",
        required=True,
        dest="platform",
        choices=list(PLATFORM_FROM_STR.keys()),
        help=("Cloud platform to build image for"),
    )
    parser.add_argument(
        "--image",
        required=True,
        dest="image",
        help=("Image to build from, defaults to daily image"),
    )
    parser.add_argument(
        "--user-data",
        dest="user_data",
        type=FileType("r"),
        default=None,
        help="Optional user-data to send to the instances launched",
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
    user_data = args.user_data.read() if args.user_data else None
    temp_dir = TemporaryDirectory(delete=False)
    launch_instances(
        temp_dir.name,
        sample_count=args.sample_count,
        image=args.image,
        platform=args.platform,
        user_data=user_data,
    )
    print(f"Results saved to: {temp_dir}")
