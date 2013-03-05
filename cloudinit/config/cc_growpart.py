# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os.path
import os
import re
import stat

from cloudinit.settings import PER_ALWAYS
from cloudinit import log as logging
from cloudinit import util

frequency = PER_ALWAYS

DEFAULT_CONFIG = {
   'mode': 'auto',
   'devices': ['/'],
}

LOG = logging.getLogger(__name__)

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


class ResizeParted(object):
    def available(self):
        myenv = os.environ.copy()
        myenv['LANG'] = 'C'

        try:
            (out, _err) = util.subp(["parted", "--help"], env=myenv)
            if re.search("COMMAND.*resizepart\s+", out, re.DOTALL):
                return True

        except util.ProcessExecutionError:
            pass
        return False

    def resize(self, blockdev, part):
        try:
            util.subp(["parted", "resizepart", blockdev, part])
        except util.ProcessExecutionError as e:
            raise ResizeFailedException(e)


class ResizeGrowPart(object):
    def available(self):
        myenv = os.environ.copy()
        myenv['LANG'] = 'C'

        try:
            (out, _err) = util.subp(["growpart", "--help"], env=myenv)
            if re.search("--update\s+", out, re.DOTALL):
                return True

        except util.ProcessExecutionError:
            pass
        return False

    def resize(self, blockdev, part):
        try:
            util.subp(["growpart", '--dry-run', blockdev, part])
        except util.ProcessExecutionError as e:
            if e.exit_code != 1:
                logexc(LOG, ("Failed growpart --dry-run for (%s, %s)" %
                             (blockdev, part)))
                raise ResizeFailedException(e)
            LOG.debug("no change necessary on (%s,%s)" % (blockdev, part))
            return

        try:
            util.subp(["growpart", blockdev, part])
        except util.ProcessExecutionError as e:
            logexc(LOG, "Failed: growpart %s %s" % (blockdev, part))
            raise ResizeFailedException(e)


def device_part_info(devpath):
    # convert an entry in /dev/ to parent disk and partition number

    # input of /dev/vdb or /dev/disk/by-label/foo
    # rpath is hopefully a real-ish path in /dev (vda, sdb..)
    rpath = os.path.realpath(devpath)

    bname = os.path.basename(rpath)
    syspath = "/sys/class/block/%s" % bname

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
        return result[0]


def resize_devices(resizer, devices):
    resized = []
    for devent in devices:
        try:
            blockdev = devent2dev(devent)
        except ValueError as e:
            LOG.debug("unable to turn %s into device: %s" % (devent, e))
            continue

        try:
            statret = os.stat(blockdev)
        except OSError as e:
            LOG.debug("device '%s' for '%s' failed stat" %
                      (blockdev, devent))
            continue
            
        if not stat.S_ISBLK(statret.st_mode):
            LOG.debug("device '%s' for '%s' is not a block device" %
                      (blockdev, devent))
            continue

        try:
            (disk, ptnum) = device_part_info(blockdev)
        except (TypeError, ValueError) as e:
            LOG.debug("failed to get part_info for (%s, %s): %s" %
                      (devent, blockdev, e))
            continue

        try:
            resizer.resize(disk, ptnum)
        except ResizeFailedException as e:
            LOG.warn("failed to resize: devent=%s, disk=%s, ptnum=%s: %s",
                     devent, disk, ptnum, e)

        resized.append(devent)

    return resized


def handle(name, cfg, _cloud, log, _args):
    if 'growpart' not in cfg:
        log.debug("No 'growpart' entry in cfg.  Using default: %s" %
                  DEFAULT_CONFIG)
        cfg['growpart'] = DEFAULT_CONFIG

    mycfg = cfg.get('growpart')
    if not isinstance(mycfg, dict):
        log.warn("'growpart' in config was not a dict")
        return

    mode = mycfg.get('mode')
    if util.is_false(mode):
        log.debug("growpart disabled: mode=%s" % mode)
        return

    devices = util.get_cfg_option_list(cfg, "devices", ["/"])
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

    resized = resize_devices(resizer, devices)
    log.debug("resized: %s" % resized)

RESIZERS = (('parted', ResizeParted), ('growpart', ResizeGrowPart))

