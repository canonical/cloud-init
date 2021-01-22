# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Growpart
--------
**Summary:** grow partitions

Growpart resizes partitions to fill the available disk space.
This is useful for cloud instances with a larger amount of disk space available
than the pristine image uses, as it allows the instance to automatically make
use of the extra space.

The devices on which to run growpart are specified as a list under the
``devices`` key. Each entry in the devices list can be either the path to the
device's mountpoint in the filesystem or a path to the block device in
``/dev``.

The utility to use for resizing can be selected using the ``mode`` config key.
If the ``mode`` key is set to ``auto``, then any available utility (either
``growpart`` or BSD ``gpart``) will be used. If neither utility is available,
no error will be raised. If ``mode`` is set to ``growpart``, then the
``growpart`` utility will be used. If this utility is not available on the
system, this will result in an error. If ``mode`` is set to ``off`` or
``false``, then ``cc_growpart`` will take no action.

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

**Internal name:** ``cc_growpart``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    growpart:
        mode: <auto/growpart/off/false>
        devices:
            - "/"
            - "/dev/vdb1"
        ignore_growroot_disabled: <true/false>
"""

import os
import os.path
import re
import stat

from functools import lru_cache
from cloudinit import log as logging
from cloudinit.settings import PER_ALWAYS
from cloudinit import subp
from cloudinit import util

frequency = PER_ALWAYS

DEFAULT_CONFIG = {
    'mode': 'auto',
    'devices': ['/'],
    'ignore_growroot_disabled': False,
}


class RESIZE(object):
    SKIPPED = "SKIPPED"
    CHANGED = "CHANGED"
    NOCHANGE = "NOCHANGE"
    FAILED = "FAILED"


LOG = logging.getLogger(__name__)


@lru_cache()
def is_lvm_lv(devpath):
    if util.is_Linux():
        # all lvm lvs will have a realpath as a 'dm-*' name.
        rpath = os.path.realpath(devpath)
        if not os.path.basename(rpath).startswith("dm-"):
            return False
        out, _ = subp.subp("udevadm", "info", devpath)
        # lvs should have DM_LV_NAME=<lvmuuid> and also DM_VG_NAME
        return 'DM_LV_NAME=' in out
    else:
        return False


@lru_cache()
def get_pvs_for_lv(devpath):
    myenv = {'LANG': 'C'}

    if util.is_Linux():
        try:
            (out, _err) = subp.subp(["lvm", "lvs", devpath, "--options=vgname",
                                     "--noheadings"], update_env=myenv)
            vgname = out.strip()
        except subp.ProcessExecutionError as e:
            if e.exit_code != 0:
                util.logexc(LOG, "Failed: can't get Volume Group information "
                            "from %s", devpath)
                raise ResizeFailedException(e) from e

        try:
            (out, _err) = subp.subp(["lvm", "vgs", vgname, "--options=pvname",
                                     "--noheadings"], update_env=myenv)
            pvs = [p.strip() for p in out.splitlines()]
            if len(pvs) > 1:
                util.logexc(LOG, "Do not know how to resize multiple Physical"
                            " Volumes")
            else:
                return pvs[0]
        except subp.ProcessExecutionError as e:
            if e.exit_code != 0:
                util.logexc(LOG, "Failed: can't get Physical Volume "
                            "information from Volume Group %s", vgname)
                raise ResizeFailedException(e) from e
    else:
        return False


def resizer_factory(mode):
    resize_class = None
    if mode == "auto":
        for (_name, resizer) in RESIZERS:
            cur = resizer()
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

        mclass = mmap[mode]()
        if mclass.available():
            resize_class = mclass

        if not resize_class:
            raise ValueError("mode %s not available" % mode)

    return resize_class


class ResizeFailedException(Exception):
    pass


class ResizeGrowPart(object):
    def available(self):
        myenv = os.environ.copy()
        myenv['LANG'] = 'C'

        try:
            (out, _err) = subp.subp(["growpart", "--help"], env=myenv)
            if re.search(r"--update\s+", out):
                return True

        except subp.ProcessExecutionError:
            pass
        return False

    def resize(self, diskdev, partnum, partdev):
        before = get_size(partdev)
        try:
            subp.subp(["growpart", '--dry-run', diskdev, partnum])
        except subp.ProcessExecutionError as e:
            if e.exit_code != 1:
                util.logexc(LOG, "Failed growpart --dry-run for (%s, %s)",
                            diskdev, partnum)
                raise ResizeFailedException(e) from e
            return (before, before)

        try:
            subp.subp(["growpart", diskdev, partnum])
        except subp.ProcessExecutionError as e:
            util.logexc(LOG, "Failed: growpart %s %s", diskdev, partnum)
            raise ResizeFailedException(e) from e

        return (before, get_size(partdev))


class ResizeGpart(object):
    def available(self):
        myenv = os.environ.copy()
        myenv['LANG'] = 'C'

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


def device_part_info(devpath, is_lvm):
    # convert an entry in /dev/ to parent disk and partition number

    # input of /dev/vdb or /dev/disk/by-label/foo
    # rpath is hopefully a real-ish path in /dev (vda, sdb..)
    rpath = os.path.realpath(devpath)

    # first check if this is an LVM and get its PVs
    if is_lvm:
        rpath = get_pvs_for_lv(devpath)

    bname = os.path.basename(rpath)
    syspath = "/sys/class/block/%s" % bname

    # FreeBSD doesn't know of sysfs so just get everything we need from
    # the device, like /dev/vtbd0p2.
    if util.is_FreeBSD():
        freebsd_part = "/dev/" + util.find_freebsd_part(devpath)
        m = re.search('^(/dev/.+)p([0-9])$', freebsd_part)
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
    return diskdevpath, ptnum


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
    if (dev == "/dev/root" and not container):
        dev = util.rootdev_from_cmdline(util.get_cmdline())
        if dev is None:
            if os.path.exists(dev):
                # if /dev/root exists, but we failed to convert
                # that to a "real" /dev/ path device, then return it.
                return dev
            raise ValueError("Unable to find device '/dev/root'")
    return dev


def resize_devices(resizer, devices):
    # returns a tuple of tuples containing (entry-in-devices, action, message)
    info = []
    for devent in devices:
        try:
            blockdev = devent2dev(devent)
        except ValueError as e:
            info.append((devent, RESIZE.SKIPPED,
                         "unable to convert to device: %s" % e,))
            continue

        try:
            statret = os.stat(blockdev)
        except OSError as e:
            info.append((devent, RESIZE.SKIPPED,
                         "stat of '%s' failed: %s" % (blockdev, e),))
            continue

        if (not stat.S_ISBLK(statret.st_mode) and
                not stat.S_ISCHR(statret.st_mode)):
            info.append((devent, RESIZE.SKIPPED,
                         "device '%s' not a block device" % blockdev,))
            continue

        is_lvm = is_lvm_lv(blockdev)
        try:
            disk, ptnum = device_part_info(blockdev, is_lvm)
        except (TypeError, ValueError) as e:
            info.append((devent, RESIZE.SKIPPED,
                         "device_part_info(%s) failed: %s" % (blockdev, e),))
            continue

        try:
            (old, new) = resizer.resize(disk, ptnum, blockdev)
            if old == new:
                info.append((devent, RESIZE.NOCHANGE,
                             "no change necessary (%s, %s)" % (disk, ptnum),))
            else:
                info.append((devent, RESIZE.CHANGED,
                             "changed (%s, %s) from %s to %s" %
                             (disk, ptnum, old, new),))

        except ResizeFailedException as e:
            info.append((devent, RESIZE.FAILED,
                         "failed to resize: disk=%s, ptnum=%s: %s" %
                         (disk, ptnum, e),))

        if is_lvm and isinstance(resizer, ResizeGrowPart):
            try:
                if len(devices) == 1:
                    (_out, _err) = subp.subp(["lvm", "lvextend", "--extents=",
                                             "100%FREE", blockdev],
                                             update_env={'LANG': 'C'})
                    info.append((devent, RESIZE.CHANGED,
                                 "Logical Volume %s extended" % devices[0],))
                else:
                    raise ValueError("Exactly one device should be configured "
                                     "to be resized when using LVM. More than "
                                     "one configured: %s" % devices)
            except (subp.ProcessExecutionError, ValueError) as e:
                info.append((devent, RESIZE.NOCHANGE,
                             "Logical Volume %s resize failed: %s" %
                             (blockdev, e),))

    return info


def handle(_name, cfg, _cloud, log, _args):
    if 'growpart' not in cfg:
        log.debug("No 'growpart' entry in cfg.  Using default: %s" %
                  DEFAULT_CONFIG)
        cfg['growpart'] = DEFAULT_CONFIG

    mycfg = cfg.get('growpart')
    if not isinstance(mycfg, dict):
        log.warning("'growpart' in config was not a dict")
        return

    mode = mycfg.get('mode', "auto")
    if util.is_false(mode):
        log.debug("growpart disabled: mode=%s" % mode)
        return

    if util.is_false(mycfg.get('ignore_growroot_disabled', False)):
        if os.path.isfile("/etc/growroot-disabled"):
            log.debug("growpart disabled: /etc/growroot-disabled exists")
            log.debug("use ignore_growroot_disabled to ignore")
            return

    devices = util.get_cfg_option_list(mycfg, "devices", ["/"])
    if not len(devices):
        log.debug("growpart: empty device list")
        return

    try:
        resizer = resizer_factory(mode)
    except (ValueError, TypeError) as e:
        log.debug("growpart unable to find resizer for '%s': %s" % (mode, e))
        if mode != "auto":
            raise e
        return

    resized = util.log_time(logfunc=log.debug, msg="resize_devices",
                            func=resize_devices, args=(resizer, devices))
    for (entry, action, msg) in resized:
        if action == RESIZE.CHANGED:
            log.info("'%s' resized: %s" % (entry, msg))
        else:
            log.debug("'%s' %s: %s" % (entry, action, msg))


RESIZERS = (('growpart', ResizeGrowPart), ('gpart', ResizeGpart))

# vi: ts=4 expandtab
