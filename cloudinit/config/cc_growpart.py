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
import stat

from cloudinit.settings import PER_ALWAYS
from cloudinit import util

frequency = PER_ALWAYS


def device_part_info(devpath, log):
    # convert an entry in /dev/ to parent disk and partition number

    # input of /dev/vdb or /dev/disk/by-label/foo
    # rpath is hopefully a real-ish path in /dev (vda, sdb..)
    rpath = os.path.realpath(devpath)

    bname = os.path.basename(rpath)
    syspath = "/sys/class/block/%s" % bname

    if not os.path.exists(syspath):
        log.debug("%s had no syspath (%s)" % (devpath, syspath))
        return None

    ptpath = os.path.join(syspath, "partition")
    if not os.path.exists(ptpath):
        log.debug("%s not a partition" % devpath)
        return None

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


def handle(name, cfg, _cloud, log, args):
    if len(args) != 0:
        growroot = args[0]
    else:
        growroot = util.get_cfg_option_bool(cfg, "growroot", True)

    if not growroot:
        log.debug("Skipping module named %s, growroot disabled", name)
        return

    resize_what = "/"
    result = util.get_mount_info(resize_what, log)
    if not result:
        log.warn("Could not determine filesystem type of %s" % resize_what)
        return

    (devpth, _fs_type, mount_point) = result

    # Ensure the path is a block device.
    if not stat.S_ISBLK(os.stat(devpth).st_mode):
        log.debug("The %s device which was found for mount point %s for %s "
                  "is not a block device" % (devpth, mount_point, resize_what))
        return

    result = device_part_info(devpth, log)
    if not result:
        log.debug("%s did not look like a partition" % devpth)

    (disk, ptnum) = result

    try:
        (out, _err) = util.subp(["growpart", disk, ptnum], rcs=[0, 1])
    except util.ProcessExecutionError as e:
        log.warn("growpart failed: %s/%s" % (e.stdout, e.stderr))
        return

    log.debug("growpart said: %s" % out)
