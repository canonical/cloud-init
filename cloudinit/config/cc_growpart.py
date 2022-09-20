# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Growpart: Grow partitions"""

import base64
import copy
import json
import os
import os.path
import re
import stat
from abc import ABC, abstractmethod
from contextlib import suppress
from logging import Logger
from pathlib import Path
from textwrap import dedent
from typing import Tuple

from cloudinit import log as logging
from cloudinit import subp, temp_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.settings import PER_ALWAYS

MODULE_DESCRIPTION = """\
Growpart resizes partitions to fill the available disk space.
This is useful for cloud instances with a larger amount of disk space available
than the pristine image uses, as it allows the instance to automatically make
use of the extra space.

The devices on which to run growpart are specified as a list under the
``devices`` key.

There is some functionality overlap between this module and the ``growroot``
functionality of ``cloud-initramfs-tools``. However, there are some situations
where one tool is able to function and the other is not. The default
configuration for both should work for most cloud instances. To explicitly
prevent ``cloud-initramfs-tools`` from running ``growroot``, the file
``/etc/growroot-disabled`` can be created. By default, both ``growroot`` and
``cc_growpart`` will check for the existence of this file and will not run if
it is present. However, this file can be ignored for ``cc_growpart`` by setting
``ignore_growroot_disabled`` to ``true``. For more information on
``cloud-initramfs-tools`` see: https://launchpad.net/cloud-initramfs-tools

Growpart is enabled by default on the root partition. The default config for
growpart is::

    growpart:
      mode: auto
      devices: ["/"]
      ignore_growroot_disabled: false
"""
frequency = PER_ALWAYS
meta: MetaSchema = {
    "id": "cc_growpart",
    "name": "Growpart",
    "title": "Grow partitions",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "examples": [
        dedent(
            """\
            growpart:
              mode: auto
              devices: ["/"]
              ignore_growroot_disabled: false
            """
        ),
        dedent(
            """\
            growpart:
              mode: growpart
              devices:
                - "/"
                - "/dev/vdb1"
              ignore_growroot_disabled: true
            """
        ),
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)

DEFAULT_CONFIG = {
    "mode": "auto",
    "devices": ["/"],
    "ignore_growroot_disabled": False,
}

KEYDATA_PATH = Path("/cc_growpart_keydata")


class RESIZE:
    SKIPPED = "SKIPPED"
    CHANGED = "CHANGED"
    NOCHANGE = "NOCHANGE"
    FAILED = "FAILED"


LOG = logging.getLogger(__name__)


def resizer_factory(mode: str, distro: Distro):
    resize_class = None
    if mode == "auto":
        for (_name, resizer) in RESIZERS:
            cur = resizer(distro)
            if cur.available():
                resize_class = cur
                break

        if not resize_class:
            raise ValueError("No resizers available")

    else:
        mmap = {}
        for (k, v) in RESIZERS:
            mmap[k] = v

        if mode not in mmap:
            raise TypeError("unknown resize mode %s" % mode)

        mclass = mmap[mode](distro)
        if mclass.available():
            resize_class = mclass

        if not resize_class:
            raise ValueError("mode %s not available" % mode)

    return resize_class


class ResizeFailedException(Exception):
    pass


class Resizer(ABC):
    def __init__(self, distro: Distro):
        self._distro = distro

    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def resize(self, diskdev, partnum, partdev):
        ...


class ResizeGrowPart(Resizer):
    def available(self):
        myenv = os.environ.copy()
        myenv["LANG"] = "C"

        try:
            (out, _err) = subp.subp(["growpart", "--help"], env=myenv)
            if re.search(r"--update\s+", out):
                return True

        except subp.ProcessExecutionError:
            pass
        return False

    def resize(self, diskdev, partnum, partdev):
        myenv = os.environ.copy()
        myenv["LANG"] = "C"
        before = get_size(partdev)

        # growpart uses tmp dir to store intermediate states
        # and may conflict with systemd-tmpfiles-clean
        tmp_dir = self._distro.get_tmp_exec_path()
        with temp_utils.tempdir(dir=tmp_dir, needs_exe=True) as tmpd:
            growpart_tmp = os.path.join(tmpd, "growpart")
            if not os.path.exists(growpart_tmp):
                os.mkdir(growpart_tmp, 0o700)
            myenv["TMPDIR"] = growpart_tmp
            try:
                subp.subp(
                    ["growpart", "--dry-run", diskdev, partnum], env=myenv
                )
            except subp.ProcessExecutionError as e:
                if e.exit_code != 1:
                    util.logexc(
                        LOG,
                        "Failed growpart --dry-run for (%s, %s)",
                        diskdev,
                        partnum,
                    )
                    raise ResizeFailedException(e) from e
                return (before, before)

            try:
                subp.subp(["growpart", diskdev, partnum], env=myenv)
            except subp.ProcessExecutionError as e:
                util.logexc(LOG, "Failed: growpart %s %s", diskdev, partnum)
                raise ResizeFailedException(e) from e

        return (before, get_size(partdev))


class ResizeGpart(Resizer):
    def available(self):
        myenv = os.environ.copy()
        myenv["LANG"] = "C"

        try:
            (_out, err) = subp.subp(["gpart", "help"], env=myenv, rcs=[0, 1])
            if re.search(r"gpart recover ", err):
                return True

        except subp.ProcessExecutionError:
            pass
        return False

    def resize(self, diskdev, partnum, partdev):
        """
        GPT disks store metadata at the beginning (primary) and at the
        end (secondary) of the disk. When launching an image with a
        larger disk compared to the original image, the secondary copy
        is lost. Thus, the metadata will be marked CORRUPT, and need to
        be recovered.
        """
        try:
            subp.subp(["gpart", "recover", diskdev])
        except subp.ProcessExecutionError as e:
            if e.exit_code != 0:
                util.logexc(LOG, "Failed: gpart recover %s", diskdev)
                raise ResizeFailedException(e) from e

        before = get_size(partdev)
        try:
            subp.subp(["gpart", "resize", "-i", partnum, diskdev])
        except subp.ProcessExecutionError as e:
            util.logexc(LOG, "Failed: gpart resize -i %s %s", partnum, diskdev)
            raise ResizeFailedException(e) from e

        return (before, get_size(partdev))


def get_size(filename):
    fd = os.open(filename, os.O_RDONLY)
    try:
        return os.lseek(fd, 0, os.SEEK_END)
    finally:
        os.close(fd)


def device_part_info(devpath):
    # convert an entry in /dev/ to parent disk and partition number

    # input of /dev/vdb or /dev/disk/by-label/foo
    # rpath is hopefully a real-ish path in /dev (vda, sdb..)
    rpath = os.path.realpath(devpath)

    bname = os.path.basename(rpath)
    syspath = "/sys/class/block/%s" % bname

    # FreeBSD doesn't know of sysfs so just get everything we need from
    # the device, like /dev/vtbd0p2.
    if util.is_FreeBSD():
        freebsd_part = "/dev/" + util.find_freebsd_part(devpath)
        m = re.search("^(/dev/.+)p([0-9])$", freebsd_part)
        return (m.group(1), m.group(2))
    elif util.is_DragonFlyBSD():
        dragonflybsd_part = "/dev/" + util.find_dragonflybsd_part(devpath)
        m = re.search("^(/dev/.+)s([0-9])$", dragonflybsd_part)
        return (m.group(1), m.group(2))

    if not os.path.exists(syspath):
        raise ValueError("%s had no syspath (%s)" % (devpath, syspath))

    ptpath = os.path.join(syspath, "partition")
    if not os.path.exists(ptpath):
        raise TypeError("%s not a partition" % devpath)

    ptnum = util.load_file(ptpath).rstrip()

    # for a partition, real syspath is something like:
    # /sys/devices/pci0000:00/0000:00:04.0/virtio1/block/vda/vda1
    rsyspath = os.path.realpath(syspath)
    disksyspath = os.path.dirname(rsyspath)

    diskmajmin = util.load_file(os.path.join(disksyspath, "dev")).rstrip()
    diskdevpath = os.path.realpath("/dev/block/%s" % diskmajmin)

    # diskdevpath has something like 253:0
    # and udev has put links in /dev/block/253:0 to the device name in /dev/
    return (diskdevpath, ptnum)


def devent2dev(devent):
    if devent.startswith("/dev/"):
        return devent
    else:
        result = util.get_mount_info(devent)
        if not result:
            raise ValueError("Could not determine device of '%s' % dev_ent")
        dev = result[0]

    container = util.is_container()

    # Ensure the path is a block device.
    if dev == "/dev/root" and not container:
        dev = util.rootdev_from_cmdline(util.get_cmdline())
        if dev is None:
            if os.path.exists(dev):
                # if /dev/root exists, but we failed to convert
                # that to a "real" /dev/ path device, then return it.
                return dev
            raise ValueError("Unable to find device '/dev/root'")
    return dev


def get_mapped_device(blockdev):
    """Returns underlying block device for a mapped device.

    If it is mapped, blockdev will usually take the form of
    /dev/mapper/some_name

    If blockdev is a symlink pointing to a /dev/dm-* device, return
    the device pointed to. Otherwise, return None.
    """
    realpath = os.path.realpath(blockdev)
    if realpath.startswith("/dev/dm-"):
        LOG.debug("%s is a mapped device pointing to %s", blockdev, realpath)
        return realpath
    return None


def is_encrypted(blockdev, partition) -> bool:
    """
    Check if a device is an encrypted device. blockdev should have
    a /dev/dm-* path whereas partition is something like /dev/sda1.
    """
    if not subp.which("cryptsetup"):
        LOG.debug("cryptsetup not found. Assuming no encrypted partitions")
        return False
    try:
        subp.subp(["cryptsetup", "status", blockdev])
    except subp.ProcessExecutionError as e:
        if e.exit_code == 4:
            LOG.debug("Determined that %s is not encrypted", blockdev)
        else:
            LOG.warning(
                "Received unexpected exit code %s from "
                "cryptsetup status. Assuming no encrypted partitions.",
                e.exit_code,
            )
        return False
    with suppress(subp.ProcessExecutionError):
        subp.subp(["cryptsetup", "isLuks", partition])
        LOG.debug("Determined that %s is encrypted", blockdev)
        return True
    return False


def get_underlying_partition(blockdev):
    command = ["dmsetup", "deps", "--options=devname", blockdev]
    dep: str = subp.subp(command)[0]  # pyright: ignore
    # Returned result should look something like:
    # 1 dependencies : (vdb1)
    if not dep.startswith("1 depend"):
        raise RuntimeError(
            f"Expecting '1 dependencies' from 'dmsetup'. Received: {dep}"
        )
    try:
        return f'/dev/{dep.split(": (")[1].split(")")[0]}'
    except IndexError as e:
        raise RuntimeError(
            f"Ran `{command}`, but received unexpected stdout: `{dep}`"
        ) from e


def resize_encrypted(blockdev, partition) -> Tuple[str, str]:
    """Use 'cryptsetup resize' to resize LUKS volume.

    The loaded keyfile is json formatted with 'key' and 'slot' keys.
    key is base64 encoded. Example:
    {"key":"XFmCwX2FHIQp0LBWaLEMiHIyfxt1SGm16VvUAVledlY=","slot":5}
    """
    if not KEYDATA_PATH.exists():
        return (RESIZE.SKIPPED, "No encryption keyfile found")
    try:
        with KEYDATA_PATH.open() as f:
            keydata = json.load(f)
        key = keydata["key"]
        decoded_key = base64.b64decode(key)
        slot = keydata["slot"]
    except Exception as e:
        raise RuntimeError(
            "Could not load encryption key. This is expected if "
            "the volume has been previously resized."
        ) from e

    try:
        subp.subp(
            ["cryptsetup", "--key-file", "-", "resize", blockdev],
            data=decoded_key,
        )
    finally:
        try:
            subp.subp(
                [
                    "cryptsetup",
                    "luksKillSlot",
                    "--batch-mode",
                    partition,
                    str(slot),
                ]
            )
        except subp.ProcessExecutionError as e:
            LOG.warning(
                "Failed to kill luks slot after resizing encrypted volume: %s",
                e,
            )
        try:
            KEYDATA_PATH.unlink()
        except Exception:
            util.logexc(
                LOG, "Failed to remove keyfile after resizing encrypted volume"
            )

    return (
        RESIZE.CHANGED,
        f"Successfully resized encrypted volume '{blockdev}'",
    )


def resize_devices(resizer, devices):
    # returns a tuple of tuples containing (entry-in-devices, action, message)
    devices = copy.copy(devices)
    info = []

    while devices:
        devent = devices.pop(0)
        try:
            blockdev = devent2dev(devent)
        except ValueError as e:
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "unable to convert to device: %s" % e,
                )
            )
            continue

        try:
            statret = os.stat(blockdev)
        except OSError as e:
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "stat of '%s' failed: %s" % (blockdev, e),
                )
            )
            continue

        if not stat.S_ISBLK(statret.st_mode) and not stat.S_ISCHR(
            statret.st_mode
        ):
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "device '%s' not a block device" % blockdev,
                )
            )
            continue

        underlying_blockdev = get_mapped_device(blockdev)
        if underlying_blockdev:
            try:
                # We need to resize the underlying partition first
                partition = get_underlying_partition(blockdev)
                if is_encrypted(underlying_blockdev, partition):
                    if partition not in [x[0] for x in info]:
                        # We shouldn't attempt to resize this mapped partition
                        # until the underlying partition is resized, so re-add
                        # our device to the beginning of the list we're
                        # iterating over, then add our underlying partition
                        # so it can get processed first
                        devices.insert(0, devent)
                        devices.insert(0, partition)
                        continue
                    status, message = resize_encrypted(blockdev, partition)
                    info.append(
                        (
                            devent,
                            status,
                            message,
                        )
                    )
                else:
                    info.append(
                        (
                            devent,
                            RESIZE.SKIPPED,
                            f"Resizing mapped device ({blockdev}) skipped "
                            "as it is not encrypted.",
                        )
                    )
            except Exception as e:
                info.append(
                    (
                        devent,
                        RESIZE.FAILED,
                        f"Resizing encrypted device ({blockdev}) failed: {e}",
                    )
                )
            # At this point, we WON'T resize a non-encrypted mapped device
            # though we should probably grow the ability to
            continue
        try:
            (disk, ptnum) = device_part_info(blockdev)
        except (TypeError, ValueError) as e:
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "device_part_info(%s) failed: %s" % (blockdev, e),
                )
            )
            continue

        try:
            (old, new) = resizer.resize(disk, ptnum, blockdev)
            if old == new:
                info.append(
                    (
                        devent,
                        RESIZE.NOCHANGE,
                        "no change necessary (%s, %s)" % (disk, ptnum),
                    )
                )
            else:
                info.append(
                    (
                        devent,
                        RESIZE.CHANGED,
                        "changed (%s, %s) from %s to %s"
                        % (disk, ptnum, old, new),
                    )
                )

        except ResizeFailedException as e:
            info.append(
                (
                    devent,
                    RESIZE.FAILED,
                    "failed to resize: disk=%s, ptnum=%s: %s"
                    % (disk, ptnum, e),
                )
            )

    return info


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if "growpart" not in cfg:
        log.debug(
            "No 'growpart' entry in cfg.  Using default: %s" % DEFAULT_CONFIG
        )
        cfg["growpart"] = DEFAULT_CONFIG

    mycfg = cfg.get("growpart")
    if not isinstance(mycfg, dict):
        log.warning("'growpart' in config was not a dict")
        return

    mode = mycfg.get("mode", "auto")
    if util.is_false(mode):
        if mode != "off":
            log.warning(
                f"DEPRECATED: growpart mode '{mode}' is deprecated. "
                "Use 'off' instead."
            )
        log.debug("growpart disabled: mode=%s" % mode)
        return

    if util.is_false(mycfg.get("ignore_growroot_disabled", False)):
        if os.path.isfile("/etc/growroot-disabled"):
            log.debug("growpart disabled: /etc/growroot-disabled exists")
            log.debug("use ignore_growroot_disabled to ignore")
            return

    devices = util.get_cfg_option_list(mycfg, "devices", ["/"])
    if not len(devices):
        log.debug("growpart: empty device list")
        return

    try:
        resizer = resizer_factory(mode, cloud.distro)
    except (ValueError, TypeError) as e:
        log.debug("growpart unable to find resizer for '%s': %s" % (mode, e))
        if mode != "auto":
            raise e
        return

    resized = util.log_time(
        logfunc=log.debug,
        msg="resize_devices",
        func=resize_devices,
        args=(resizer, devices),
    )
    for (entry, action, msg) in resized:
        if action == RESIZE.CHANGED:
            log.info("'%s' resized: %s" % (entry, msg))
        else:
            log.debug("'%s' %s: %s" % (entry, action, msg))


RESIZERS = (("growpart", ResizeGrowPart), ("gpart", ResizeGpart))

# vi: ts=4 expandtab
