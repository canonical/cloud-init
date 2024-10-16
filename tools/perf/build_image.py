#!/usr/bin/env python3
"""Basic image build tool


REQUIREMENTS:
- sudo permissions to mount ISO images
- mount-image-callback utility from cloud-image-utils deb package
"""

# ruff: noqa: E501

import logging
import os
import shutil
import glob
import tempfile
from argparse import ArgumentParser

from cloudinit import subp
from tests.integration_tests import releases

import pycloudlib

PLATFORM_FROM_STR = {
    "qemu": pycloudlib.Qemu,
    "gce": pycloudlib.GCE,
    "ec2": pycloudlib.EC2,
    "lxd_container": pycloudlib.LXDContainer,
    "lxd_vm": pycloudlib.LXDVirtualMachine,
}


def update_cloud_init_in_container_image(
    build_dir: str,
    img_path: str,
    deb_path: str,
    series: str,
    suffix=".modified",
) -> str:
    alias = f"{img_path}{suffix}"
    mount_cmds = [
        [
            "sudo",
            "mount",
            "-t",
            "proc",
            "/proc",
            "squashfs-root/proc/",
        ],
        [
            "sudo",
            "mount",
            "--bind",
            "/dev",
            "squashfs-root/dev/",
        ],
        [
            "sudo",
            "mount",
            "--bind",
            "/sys",
            "squashfs-root/sys/",
        ],
        [
            "sudo",
            "mount",
            "--bind",
            "/run",
            "./squashfs-root/run/",
        ],
        [
            "sudo",
            "mount",
            "--bind",
            "/tmp",
            "./squashfs-root/tmp/",
        ],
    ]
    umount_cmds = [
        [
            "sudo",
            "umount",
            "./squashfs-root/proc",
        ],
        [
            "sudo",
            "umount",
            "./squashfs-root/dev/",
        ],
        [
            "sudo",
            "umount",
            "./squashfs-root/sys/",
        ],
        [
            "sudo",
            "umount",
            "./squashfs-root/run/",
        ],
        [
            "sudo",
            "umount",
            "./squashfs-root/tmp/",
        ],
    ]
    subp.subp(
        [
            "lxc",
            "image",
            "export",
            img_path,
            build_dir,
        ]
    )
    # this should only have one file each
    meta = glob.glob(f"{build_dir}/*.tar.xz")[0]
    try:
        squashfs = glob.glob(f"{build_dir}/*.squashfs")[0]
    except IndexError:
        print(f"Missing squashfs file. Is {img_path} a container?")
        os._exit(1)

    subp.subp(
        ["sudo", "unsquashfs", squashfs],
        cwd=build_dir,
    )
    subp.subp(
        [
            "sudo",
            "cp",
            deb_path,
            f"{build_dir}/squashfs-root/cloud-init.deb",
        ]
    )
    for command in mount_cmds:
        try:
            subp.subp(
                command,
                cwd=build_dir,
            )
        except Exception as e:
            print(e)
            print(command)
    if releases.Release.from_os_image(series) <= releases.NOBLE:
        # required to install isc-dhcp-client on newer releases
        subp.subp(
            [
                "sudo",
                "chroot",
                "squashfs-root/",
                "sh",
                "-c",
                "apt update",
            ],
            cwd=build_dir,
        )
    subp.subp(
        [
            "sudo",
            "chroot",
            "squashfs-root/",
            "sh",
            "-c",
            "apt install -y --allow-downgrades /cloud-init.deb",
        ],
        update_env={"DEBIAN_FRONTEND": "noninteractive"},
        cwd=build_dir,
    )
    subp.subp(
        [
            "sudo",
            "rm",
            f"{build_dir}/squashfs-root/cloud-init.deb",
        ]
    )
    for command in umount_cmds:
        try:
            subp.subp(
                command,
                cwd=build_dir,
            )
        except Exception as e:
            print(e)
            print(command)
    subp.subp(
        ["mksquashfs", "squashfs-root", "new.squashfs"],
        cwd=build_dir,
    )
    subp.subp(
        [
            "lxc",
            "image",
            "import",
            meta,
            f"{build_dir}/new.squashfs",
            f"--alias={alias}",
        ]
    )
    subp.subp(
        [
            "sudo",
            "rm",
            "-rf",
            f"{build_dir}/squashfs-root/",
        ]
    )
    return alias


def update_cloud_init_in_vm_image(
    img_path: str, deb_path: str, suffix=".modified"
) -> str:
    """Use mount-image-callback to install a known deb into an image"""
    new_img_path = os.path.basename(img_path.replace(".img", f".img{suffix}"))
    new_img_path = f"{os.getcwd()}/{new_img_path}"
    shutil.copy(img_path, new_img_path)
    subp.subp(["sync"])
    subp.subp(
        [
            "sudo",
            "mount-image-callback",
            new_img_path,
            "--",
            "sh",
            "-c",
            f"cp {deb_path} ${{MOUNTPOINT}}/.; chroot ${{MOUNTPOINT}} dpkg -i /{
                os.path.basename(deb_path)}",
        ],
    )
    return new_img_path


def get_parser():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--series",
        required=True,
        choices=[
            "bionic",
            "focal",
            "jammy",
            "lunar",
            "mantic",
            "noble",
            "oracular",
        ],
        help="Ubuntu series to test",
    )
    parser.add_argument(
        "--platform",
        required=True,
        dest="platform",
        choices=list(PLATFORM_FROM_STR.keys()),
        help=("Cloud platform to build image for"),
    )
    parser.add_argument(
        "--package",
        dest="package",
        help=("Deb path from which to install cloud-init for testing."),
    )
    parser.add_argument(
        "--image",
        dest="image",
        default="",
        help=("Image to build from, defaults to daily image"),
    )
    return parser


def assert_dependencies():
    """Fail on any missing dependencies."""
    if not all(
        [shutil.which("mount-image-callback"), shutil.which("unsquashfs")]
    ):
        raise RuntimeError(
            "Missing mount-image-callback utility. "
            "Try: apt-get install cloud-image-utils"
        )


def build_image(
    build_dir: str, deb_path: str, series: str, platform: str, image: str
):
    with PLATFORM_FROM_STR[platform](tag="examples") as cloud:
        daily = image or cloud.daily_image(release=series)
        print(
            f"--- Creating modified daily image {daily} with cloud-init"
            f" from {deb_path}"
        )
        if isinstance(cloud, pycloudlib.LXDContainer):
            out = update_cloud_init_in_container_image(
                build_dir, daily, deb_path, series, suffix=1
            )
        else:
            out = update_cloud_init_in_vm_image(daily, deb_path, suffix=1)
        print(out)
        return out


if __name__ == "__main__":
    assert_dependencies()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("qemu.qmp.protocol").setLevel(logging.WARNING)
    logging.getLogger("pycloudlib").setLevel(logging.INFO)
    logging.getLogger("paramiko.transport:Auth").setLevel(logging.INFO)
    parser = get_parser()
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp_dir:
        build_image(
            temp_dir,
            args.package,
            series=args.series,
            platform=args.platform,
            image=args.image,
        )
