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
import logging
import os
import os.path
import re
import stat
from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path
from typing import Optional, Tuple

from cloudinit import lifecycle, performance, subp, temp_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, Distro
from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS
meta: MetaSchema = {
    "id": "cc_growpart",
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "activate_by_schema_keys": [],
}

DEFAULT_CONFIG = {
    "mode": "auto",
    "devices": ["/"],
    "ignore_growroot_disabled": False,
    "resize_lv": True,
}

KEYDATA_PATH = Path("/cc_growpart_keydata")


class RESIZE:
    SKIPPED = "SKIPPED"
    CHANGED = "CHANGED"
    NOCHANGE = "NOCHANGE"
    FAILED = "FAILED"


LOG = logging.getLogger(__name__)


class ResizeFailedException(Exception):
    pass


class Resizer(ABC):
    def __init__(self, distro: Distro):
        self._distro = distro

    @abstractmethod
    def available(self, devices: list) -> bool: ...

    @abstractmethod
    def resize(self, diskdev, partnum, partdev, fs): ...


class ResizeGrowPart(Resizer):
    def available(self, devices: list):
        try:
            out = subp.subp(
                ["growpart", "--help"], update_env={"LANG": "C"}
            ).stdout
            if re.search(r"--update\s+", out):
                return True

        except subp.ProcessExecutionError:
            pass
        return False

    def resize(self, diskdev, partnum, partdev, fs):
        before = get_size(partdev, fs)

        # growpart uses tmp dir to store intermediate states
        # and may conflict with systemd-tmpfiles-clean
        tmp_dir = self._distro.get_tmp_exec_path()
        with temp_utils.tempdir(dir=tmp_dir, needs_exe=True) as tmpd:
            growpart_tmp = os.path.join(tmpd, "growpart")
            my_env = {"LANG": "C", "TMPDIR": growpart_tmp}
            if not os.path.exists(growpart_tmp):
                os.mkdir(growpart_tmp, 0o700)
            try:
                subp.subp(
                    ["growpart", "--dry-run", diskdev, partnum],
                    update_env=my_env,
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
                subp.subp(["growpart", diskdev, partnum], update_env=my_env)
            except subp.ProcessExecutionError as e:
                util.logexc(LOG, "Failed: growpart %s %s", diskdev, partnum)
                raise ResizeFailedException(e) from e

        return (before, get_size(partdev, fs))


class ResizeGrowFS(Resizer):
    """
    Use FreeBSD ``growfs`` service to grow root partition to fill available
    space, optionally adding a swap partition at the end.

    Note that the service file warns us that it uses ``awk(1)``, and as
    such requires ``/usr`` to be present. However, cloud-init is installed
    into ``/usr/local``, so we should be fine.

    We invoke the ``growfs`` with ``service growfs onestart``, so it
    doesn't need to be enabled in ``rc.conf``.
    """

    def available(self, devices: list):
        """growfs only works on the root partition"""
        return os.path.isfile("/etc/rc.d/growfs") and devices == ["/"]

    def resize(self, diskdev, partnum, partdev, fs):
        before = get_size(partdev, fs)
        try:
            self._distro.manage_service(action="onestart", service="growfs")
        except subp.ProcessExecutionError as e:
            util.logexc(LOG, "Failed: service growfs onestart")
            raise ResizeFailedException(e) from e

        return (before, get_size(partdev, fs))


class ResizeGpart(Resizer):
    def available(self, devices: list):
        try:
            err = subp.subp(
                ["gpart", "help"], update_env={"LANG": "C"}, rcs=[0, 1]
            ).stderr
            if re.search(r"gpart recover ", err):
                return True

        except subp.ProcessExecutionError:
            pass
        return False

    def resize(self, diskdev, partnum, partdev, fs):
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

        before = get_size(partdev, fs)
        try:
            subp.subp(["gpart", "resize", "-i", partnum, diskdev])
        except subp.ProcessExecutionError as e:
            util.logexc(LOG, "Failed: gpart resize -i %s %s", partnum, diskdev)
            raise ResizeFailedException(e) from e

        return (before, get_size(partdev, fs))


def resizer_factory(mode: str, distro: Distro, devices: list) -> Resizer:
    resize_class = None
    if mode == "auto":
        for _name, resizer in RESIZERS:
            cur = resizer(distro)
            if cur.available(devices=devices):
                resize_class = cur
                break

        if not resize_class:
            raise ValueError("No resizers available")

    else:
        mmap = {}
        for k, v in RESIZERS:
            mmap[k] = v

        if mode not in mmap:
            raise TypeError("unknown resize mode %s" % mode)

        mclass = mmap[mode](distro)
        if mclass.available(devices=devices):
            resize_class = mclass

        if not resize_class:
            raise ValueError("mode %s not available" % mode)

    return resize_class


def get_size(filename, fs) -> Optional[int]:
    fd = None
    try:
        fd = os.open(filename, os.O_RDONLY)
        return os.lseek(fd, 0, os.SEEK_END)
    except FileNotFoundError:
        if fs == "zfs":
            return get_zfs_size(filename)
        return None
    finally:
        if fd:
            os.close(fd)


def get_zfs_size(dataset) -> Optional[int]:
    zpool = dataset.split("/")[0]
    try:
        size, _ = subp.subp(["zpool", "get", "-Hpovalue", "size", zpool])
    except subp.ProcessExecutionError as e:
        LOG.debug("Failed: zpool get size %s: %s", zpool, e)
        return None
    return int(size.strip())


def devent2dev(devent):
    if devent.startswith("/dev/"):
        return devent, None

    result = util.get_mount_info(devent)
    if not result:
        raise ValueError("Could not determine device of '%s' % dev_ent")
    dev = result[0]
    fs = result[1]

    container = util.is_container()

    # Ensure the path is a block device.
    if dev == "/dev/root" and not container:
        dev = util.rootdev_from_cmdline(util.get_cmdline())
        if dev is None:
            if os.path.exists(dev):
                # if /dev/root exists, but we failed to convert
                # that to a "real" /dev/ path device, then return it.
                return dev, None
            raise ValueError("Unable to find device '/dev/root'")
    return dev, fs


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
        with performance.Timed(
            f"Reading {KEYDATA_PATH}"
        ), KEYDATA_PATH.open() as f:
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


def _get_vg_for_lv(lv_dev):
    """
    Return the VG name for a logical volume device,
    e.g. /dev/mapper/vg-lv or /dev/vg/lv.
    Uses `lvs --noheadings -o vg_name <lv_dev>`.
    """
    try:
        out = subp.subp(
            ["lvs", "--noheadings", "-o", "vg_name", lv_dev]
        ).stdout
        # lvs often prints whitespace padded output; take last token
        vg = out.strip().split()[-1]
        LOG.debug("lv %s belongs to vg %s", lv_dev, vg)
        return vg
    except Exception as e:
        LOG.warning("failed to get VG for %s: %s", lv_dev, e)
        raise


def _get_pvs_for_vg(vg_name):
    """
    Return list of PV device paths for a volume group,
    using `vgs -o pv_name --noheadings --separator ' ' <vg>`.
    """
    try:
        out = subp.subp(
            [
                "vgs",
                "--noheadings",
                "-o",
                "pv_name",
                "--separator",
                " ",
                vg_name,
            ]
        ).stdout
        # vgs returns space separated PV names (may include trailing spaces)
        pvs = [p for p in out.split() if p]
        LOG.debug("vg %s pvs: %s", vg_name, pvs)
        return pvs
    except Exception as e:
        LOG.warning("failed to list PVs for VG %s: %s", vg_name, e)
        raise


def _pvresize(pv_dev):
    """Run pvresize on each PV; idempotent: if it fails log and raise."""
    try:
        subp.subp(["pvresize", pv_dev])
        LOG.info("pvresize succeeded for %s", pv_dev)
        return True
    except Exception as e:
        LOG.warning("pvresize failed for %s: %s", pv_dev, e)
        raise


def _lvextend_to_free(lv_dev):
    """Extend the LV to consume all free extents in its VG."""
    try:
        subp.subp(["lvextend", "-l", "+100%FREE", lv_dev])
        LOG.info("lvextend +100%%FREE succeeded for %s", lv_dev)
        return True
    except Exception as e:
        LOG.warning("lvextend failed for %s: %s", lv_dev, e)
        raise


def resize_lvm(
    blockdev, resize_lv: bool = True, skip_pvresize: bool = False
) -> Tuple[str, str]:
    """
    High-level procedure to resize LVM logical volume
    after underlying PVs were expanded:
      - find VG for lv (devpath)
      - for each PV in VG: pvresize (unless skip_pvresize=True)
      - optionally lvextend the lv to use free space (if resize_lv=True)

    Args:
        blockdev: The logical volume device path
        resize_lv: If True, extend the LV to consume all free space in the VG.
                   If False, only resize PVs, leaving LV size unchanged.
                   Default: True (for backward compatibility).
        skip_pvresize: If True, skip pvresize (e.g., when growpart already
                       handled it). If False, run pvresize on all PVs in
                       the VG. Default: False.
    """
    LOG.info("starting LVM resize flow for %s", blockdev)
    vg = _get_vg_for_lv(blockdev)
    pvs = _get_pvs_for_vg(vg)

    # try pvresize for each PV (unless skipped, e.g., growpart already did it)
    if not skip_pvresize:
        for pv in pvs:
            try:
                _pvresize(pv)
            except Exception:
                LOG.warning(
                    "pvresize failed for %s, continuing to next PV", pv
                )
    else:
        LOG.debug(
            "Skipping pvresize for %s (already handled by partition resizer)",
            blockdev,
        )

    # extend the LV to use free space (if enabled)
    if resize_lv:
        _lvextend_to_free(blockdev)
        pv_status = (
            "PV already resized" if skip_pvresize else "PV and LV resized"
        )
        return (
            RESIZE.CHANGED,
            f"Successfully resized LVM device '{blockdev}' ({pv_status})",
        )
    else:
        LOG.info(
            "LV resize disabled for %s; %s. "
            "Free space remains available in VG for other LVs.",
            blockdev,
            "PV already resized" if skip_pvresize else "PVs were resized",
        )
        pv_status = "PV already resized" if skip_pvresize else "PV resized"
        return (
            RESIZE.CHANGED,
            f"Successfully resized LVM device '{blockdev}' "
            f"({pv_status}, LV unchanged)",
        )


def is_lvm_device(blockdev) -> bool:
    """
    Checks if a given device path points to an LVM device.
    """
    try:
        # Run lsblk to check if the device type is 'lvm'
        out = subp.subp(["lsblk", "-n", "-o", "TYPE", blockdev]).stdout
        return out.strip() == "lvm"
    except Exception as e:
        LOG.warning("Error checking if device is LVM: %s", e)
        return False


def _call_resizer(resizer, devent, disk, ptnum, blockdev, fs):
    info = []
    try:
        old, new = resizer.resize(disk, ptnum, blockdev, fs)
        if old == new:
            info.append(
                (
                    devent,
                    RESIZE.NOCHANGE,
                    "no change necessary (%s, %s)" % (disk, ptnum),
                )
            )
        elif new is None or old is None:
            msg = ""
            if disk is not None and ptnum is None:
                msg = "changed (%s, %s) size, new size is unknown" % (
                    disk,
                    ptnum,
                )
            else:
                msg = "changed (%s) size, new size is unknown" % blockdev
            info.append((devent, RESIZE.CHANGED, msg))
        else:
            msg = ""
            if disk is not None and ptnum is None:
                msg = "changed (%s, %s) from %s to %s" % (
                    disk,
                    ptnum,
                    old,
                    new,
                )
            else:
                msg = "changed (%s) from %s to %s" % (blockdev, old, new)
            info.append((devent, RESIZE.CHANGED, msg))

    except ResizeFailedException as e:
        info.append(
            (
                devent,
                RESIZE.FAILED,
                "failed to resize: disk=%s, ptnum=%s: %s" % (disk, ptnum, e),
            )
        )
    return info


def resize_devices(
    resizer: Resizer, devices, distro: Distro, resize_lv: bool = True
):
    # returns a tuple of tuples containing (entry-in-devices, action, message)
    devices = copy.copy(devices)
    info = []

    while devices:
        devent = devices.pop(0)
        disk = None
        ptnum = None

        try:
            blockdev, fs = devent2dev(devent)
        except ValueError as e:
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "unable to convert to device: %s" % e,
                )
            )
            continue

        LOG.debug("growpart found fs=%s", fs)
        # TODO: This seems to be the wrong place for this. On Linux, we the
        # `os.stat(blockdev)` call below will fail on a ZFS filesystem.
        # We then delay resizing the FS until calling cc_resizefs. Yet
        # the code here is to accommodate the FreeBSD `growfs` service.
        # Ideally we would grow the FS for both OSes in the same module.
        if fs == "zfs" and isinstance(resizer, ResizeGrowFS):
            info += _call_resizer(resizer, devent, disk, ptnum, blockdev, fs)
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

        underlying_blockdev = distro.get_mapped_device(blockdev)
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
                # If device is lvm
                elif is_lvm_device(blockdev):
                    # resize the partition firstly
                    disk, ptnum = distro.device_part_info(partition)
                    info += _call_resizer(
                        resizer, devent, disk, ptnum, partition, fs
                    )
                    try:
                        # Call the LVM resize procedure
                        # Skip pvresize if using growpart AND VG has only
                        # one PV
                        # (growpart's maybe_lvm_resize only resizes the
                        # specific partition's PV, so for multi-PV VGs we need
                        # to resize all PVs)
                        skip_pvresize = False
                        if isinstance(resizer, ResizeGrowPart):
                            try:
                                vg = _get_vg_for_lv(blockdev)
                                pvs = _get_pvs_for_vg(vg)
                                # Only skip if single PV
                                # (growpart already handled it)
                                if len(pvs) == 1:
                                    skip_pvresize = True
                                    LOG.debug(
                                        "VG %s has single PV, "
                                        "skipping pvresize "
                                        "(growpart already handled it)",
                                        vg,
                                    )
                                else:
                                    LOG.info(
                                        "VG %s has %d PVs, resizing all PVs "
                                        "(growpart only resized the "
                                        "partition's PV)",
                                        vg,
                                        len(pvs),
                                    )
                            except Exception as e:
                                LOG.warning(
                                    "Failed to check VG PV count, will resize "
                                    "all PVs: %s",
                                    e,
                                )
                                # On error, don't skip (safer to resize all)
                                skip_pvresize = False

                        status, message = resize_lvm(
                            blockdev,
                            resize_lv=resize_lv,
                            skip_pvresize=skip_pvresize,
                        )
                        info.append(
                            (
                                devent,
                                status,
                                message,
                            )
                        )
                    except Exception as e:
                        info.append(
                            (
                                devent,
                                RESIZE.FAILED,
                                f"Resizing LVM device ({blockdev}) failed: "
                                f"{e}",
                            )
                        )
                else:
                    info.append(
                        (
                            devent,
                            RESIZE.SKIPPED,
                            f"Resizing mapped device ({blockdev}) skipped "
                            f"as it is neither encrypted nor lvm.",
                        )
                    )
            except Exception as e:
                info.append(
                    (
                        devent,
                        RESIZE.FAILED,
                        f"Resizing device ({blockdev}) failed: {e}",
                    )
                )
            # At this point, we WON'T resize a non-encrypted mapped device
            # though we should probably grow the ability to
            continue
        try:
            disk, ptnum = distro.device_part_info(blockdev)
        except (TypeError, ValueError) as e:
            info.append(
                (
                    devent,
                    RESIZE.SKIPPED,
                    "device_part_info(%s) failed: %s" % (blockdev, e),
                )
            )
            continue

        info += _call_resizer(resizer, devent, disk, ptnum, blockdev, fs)

    return info


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "growpart" not in cfg:
        LOG.debug(
            "No 'growpart' entry in cfg.  Using default: %s", DEFAULT_CONFIG
        )
        cfg["growpart"] = DEFAULT_CONFIG

    mycfg = cfg.get("growpart")
    if not isinstance(mycfg, dict):
        LOG.warning("'growpart' in config was not a dict")
        return

    mode = mycfg.get("mode", "auto")
    if util.is_false(mode):
        if mode != "off":
            lifecycle.deprecate(
                deprecated=f"Growpart's 'mode' key with value '{mode}'",
                deprecated_version="22.2",
                extra_message="Use 'off' instead.",
            )
        LOG.debug("growpart disabled: mode=%s", mode)
        return

    if util.is_false(mycfg.get("ignore_growroot_disabled", False)):
        if os.path.isfile("/etc/growroot-disabled"):
            LOG.debug("growpart disabled: /etc/growroot-disabled exists")
            LOG.debug("use ignore_growroot_disabled to ignore")
            return

    devices = util.get_cfg_option_list(mycfg, "devices", ["/"])
    if not len(devices):
        LOG.debug("growpart: empty device list")
        return

    resize_lv = util.get_cfg_option_bool(mycfg, "resize_lv", True)

    try:
        resizer = resizer_factory(mode, distro=cloud.distro, devices=devices)
    except (ValueError, TypeError) as e:
        LOG.debug("growpart unable to find resizer for '%s': %s", mode, e)
        if mode != "auto":
            raise e
        return

    with performance.Timed("Resizing devices"):
        resized = resize_devices(
            resizer, devices, cloud.distro, resize_lv=resize_lv
        )
    for entry, action, msg in resized:
        if action == RESIZE.CHANGED:
            LOG.info("'%s' resized: %s", entry, msg)
        else:
            LOG.debug("'%s' %s: %s", entry, action, msg)


RESIZERS = (
    ("growpart", ResizeGrowPart),
    ("growfs", ResizeGrowFS),
    ("gpart", ResizeGpart),
)
