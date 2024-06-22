# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Resizefs: cloud-config module which resizes the filesystem"""

import errno
import logging
import os
import re
import stat
from typing import Optional

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

NOBLOCK = "noblock"

meta: MetaSchema = {
    "id": "cc_resizefs",
    "distros": [ALL_DISTROS],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)


def _resize_btrfs(mount_point, devpth):
    # If "/" is ro resize will fail. However it should be allowed since resize
    # makes everything bigger and subvolumes that are not ro will benefit.
    # Use a subvolume that is not ro to trick the resize operation to do the
    # "right" thing. The use of ".snapshot" is specific to "snapper" a generic
    # solution would be walk the subvolumes and find a rw mounted subvolume.
    if not util.mount_is_read_write(mount_point) and os.path.isdir(
        "%s/.snapshots" % mount_point
    ):
        cmd = [
            "btrfs",
            "filesystem",
            "resize",
            "max",
            "%s/.snapshots" % mount_point,
        ]
    else:
        cmd = ["btrfs", "filesystem", "resize", "max", mount_point]

    # btrfs has exclusive operations and resize may fail if btrfs is busy
    # doing one of the operations that prevents resize. As of btrfs 5.10
    # the resize operation can be queued
    btrfs_with_queue = util.Version.from_str("5.10")
    system_btrfs_ver = util.Version.from_str(
        subp.subp(["btrfs", "--version"])[0].split("v")[-1].strip()
    )
    if system_btrfs_ver >= btrfs_with_queue:
        idx = cmd.index("resize")
        cmd.insert(idx + 1, "--enqueue")

    return tuple(cmd)


def _resize_ext(mount_point, devpth):
    return ("resize2fs", devpth)


def _resize_xfs(mount_point, devpth):
    return ("xfs_growfs", mount_point)


def _resize_ufs(mount_point, devpth):
    return ("growfs", "-y", mount_point)


def _resize_zfs(mount_point, devpth):
    return ("zpool", "online", "-e", mount_point, devpth)


def _resize_hammer2(mount_point, devpth):
    return ("hammer2", "growfs", mount_point)


def _resize_bcachefs(mount_point, devpth):
    """Single device resize"""
    return ("bcachefs", "device", "resize", devpth)


def _can_skip_resize_ufs(mount_point, devpth):
    # possible errors cases on the code-path to growfs -N following:
    # https://github.com/freebsd/freebsd/blob/HEAD/sbin/growfs/growfs.c
    # This is the "good" error:
    skip_start = "growfs: requested size"
    skip_contain = "is not larger than the current filesystem size"
    # growfs exits with 1 for almost all cases up to this one.
    # This means we can't just use rcs=[0, 1] as subp parameter:
    try:
        subp.subp(["growfs", "-N", devpth])
    except subp.ProcessExecutionError as e:
        if e.stderr.startswith(skip_start) and skip_contain in e.stderr:
            # This FS is already at the desired size
            return True
        else:
            raise e
    return False


# Do not use a dictionary as these commands should be able to be used
# for multiple filesystem types if possible, e.g. one command for
# ext2, ext3 and ext4.
RESIZE_FS_PREFIXES_CMDS = [
    ("btrfs", _resize_btrfs),
    ("ext", _resize_ext),
    ("xfs", _resize_xfs),
    ("ufs", _resize_ufs),
    ("zfs", _resize_zfs),
    ("hammer2", _resize_hammer2),
    ("bcachefs", _resize_bcachefs),
]

RESIZE_FS_PRECHECK_CMDS = {"ufs": _can_skip_resize_ufs}


def get_device_info_from_zpool(zpool) -> Optional[str]:
    # zpool has 10 second timeout waiting for /dev/zfs LP: #1760173
    log_warn = LOG.debug if util.is_container() else LOG.warning
    if not os.path.exists("/dev/zfs"):
        LOG.debug("Cannot get zpool info, no /dev/zfs")
        return None
    try:
        zpoolstatus, err = subp.subp(["zpool", "status", zpool])
        if err:
            LOG.info(
                "zpool status returned error: [%s] for zpool [%s]",
                err,
                zpool,
            )
            return None
    except subp.ProcessExecutionError as err:
        log_warn("Unable to get zpool status of %s: %s", zpool, err)
        return None
    r = r".*(ONLINE).*"
    for line in zpoolstatus.split("\n"):
        if re.search(r, line) and zpool not in line and "state" not in line:
            disk = line.split()[0]
            LOG.debug('found zpool "%s" on disk %s', zpool, disk)
            return disk
    log_warn(
        "No zpool found: [%s]: out: [%s] err: %s", zpool, zpoolstatus, err
    )
    return None


def can_skip_resize(fs_type, resize_what, devpth):
    fstype_lc = fs_type.lower()
    for i, func in RESIZE_FS_PRECHECK_CMDS.items():
        if fstype_lc.startswith(i):
            return func(resize_what, devpth)
    return False


def maybe_get_writable_device_path(devpath, info):
    """Return updated devpath if the devpath is a writable block device.

    @param devpath: Requested path to the root device we want to resize.
    @param info: String representing information about the requested device.
    @param log: Logger to which logs will be added upon error.

    @returns devpath or updated devpath per kernel command line if the device
        path is a writable block device, returns None otherwise.
    """
    container = util.is_container()

    # Ensure the path is a block device.
    if (
        devpath == "/dev/root"
        and not os.path.exists(devpath)
        and not container
    ):
        devpath = util.rootdev_from_cmdline(util.get_cmdline())
        if devpath is None:
            LOG.warning("Unable to find device '/dev/root'")
            return None
        LOG.debug("Converted /dev/root to '%s' per kernel cmdline", devpath)

    if devpath == "overlayroot":
        LOG.debug("Not attempting to resize devpath '%s': %s", devpath, info)
        return None

    # FreeBSD zpool can also just use gpt/<label>
    # with that in mind we can not do an os.stat on "gpt/whatever"
    # therefore return the devpath already here.
    if devpath.startswith("gpt/"):
        LOG.debug("We have a gpt label - just go ahead")
        return devpath
    # Alternatively, our device could simply be a name as returned by gpart,
    # such as da0p3
    if not devpath.startswith("/dev/") and not os.path.exists(devpath):
        fulldevpath = "/dev/" + devpath.lstrip("/")
        LOG.debug(
            "'%s' doesn't appear to be a valid device path. Trying '%s'",
            devpath,
            fulldevpath,
        )
        devpath = fulldevpath

    try:
        statret = os.stat(devpath)
    except OSError as exc:
        if container and exc.errno == errno.ENOENT:
            LOG.debug(
                "Device '%s' did not exist in container. cannot resize: %s",
                devpath,
                info,
            )
        elif exc.errno == errno.ENOENT:
            LOG.warning(
                "Device '%s' did not exist. cannot resize: %s", devpath, info
            )
        else:
            raise exc
        return None

    if not stat.S_ISBLK(statret.st_mode) and not stat.S_ISCHR(statret.st_mode):
        if container:
            LOG.debug(
                "device '%s' not a block device in container."
                " cannot resize: %s",
                devpath,
                info,
            )
        else:
            LOG.warning(
                "device '%s' not a block device. cannot resize: %s",
                devpath,
                info,
            )
        return None
    return devpath  # The writable block devpath


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if len(args) != 0:
        resize_root = args[0]
    else:
        resize_root = util.get_cfg_option_str(cfg, "resize_rootfs", True)
    if not util.translate_bool(resize_root, addons=[NOBLOCK]):
        LOG.debug("Skipping module named %s, resizing disabled", name)
        return

    # TODO(harlowja): allow what is to be resized to be configurable??
    resize_what = "/"
    result = util.get_mount_info(resize_what, LOG)
    if not result:
        LOG.warning("Could not determine filesystem type of %s", resize_what)
        return

    (devpth, fs_type, mount_point) = result

    # if we have a zfs then our device path at this point
    # is the zfs label. For example: vmzroot/ROOT/freebsd
    # we will have to get the zpool name out of this
    # and set the resize_what variable to the zpool
    # so the _resize_zfs function gets the right attribute.
    if fs_type == "zfs":
        zpool = devpth.split("/")[0]
        devpth = get_device_info_from_zpool(zpool)
        if not devpth:
            return  # could not find device from zpool
        resize_what = zpool

    info = "dev=%s mnt_point=%s path=%s" % (devpth, mount_point, resize_what)
    LOG.debug("resize_info: %s", info)

    devpth = maybe_get_writable_device_path(devpth, info)
    if not devpth:
        return  # devpath was not a writable block device

    resizer = None
    if can_skip_resize(fs_type, resize_what, devpth):
        LOG.debug(
            "Skip resize filesystem type %s for %s", fs_type, resize_what
        )
        return

    fstype_lc = fs_type.lower()
    for (pfix, root_cmd) in RESIZE_FS_PREFIXES_CMDS:
        if fstype_lc.startswith(pfix):
            resizer = root_cmd
            break

    if not resizer:
        LOG.warning(
            "Not resizing unknown filesystem type %s for %s",
            fs_type,
            resize_what,
        )
        return

    resize_cmd = resizer(resize_what, devpth)
    LOG.debug(
        "Resizing %s (%s) using %s", resize_what, fs_type, " ".join(resize_cmd)
    )

    if resize_root == NOBLOCK:
        # Fork to a child that will run
        # the resize command
        util.fork_cb(
            util.log_time,
            logfunc=LOG.debug,
            msg="backgrounded Resizing",
            func=do_resize,
            args=(resize_cmd,),
        )
    else:
        util.log_time(
            logfunc=LOG.debug,
            msg="Resizing",
            func=do_resize,
            args=(resize_cmd,),
        )

    action = "Resized"
    if resize_root == NOBLOCK:
        action = "Resizing (via forking)"
    LOG.debug(
        "%s root filesystem (type=%s, val=%s)", action, fs_type, resize_root
    )


def do_resize(resize_cmd):
    try:
        subp.subp(resize_cmd)
    except subp.ProcessExecutionError:
        util.logexc(LOG, "Failed to resize filesystem (cmd=%s)", resize_cmd)
        raise
    # TODO(harlowja): Should we add a fsck check after this to make
    # sure we didn't corrupt anything?
