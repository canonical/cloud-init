# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import cloudinit.util as util
import subprocess
import os
import stat
import sys
import time
import tempfile
from cloudinit.CloudConfig import per_always

frequency = per_always


def handle(_name, cfg, _cloud, log, args):
    if len(args) != 0:
        resize_root = False
        if str(args[0]).lower() in ['true', '1', 'on', 'yes']:
            resize_root = True
    else:
        resize_root = util.get_cfg_option_str(cfg, "resize_rootfs", True)

    if str(resize_root).lower() in ['false', '0']:
        return

    # we use mktemp rather than mkstemp because early in boot nothing
    # else should be able to race us for this, and we need to mknod.
    devpth = tempfile.mktemp(prefix="cloudinit.resizefs.", dir="/run")

    try:
        st_dev = os.stat("/").st_dev
        dev = os.makedev(os.major(st_dev), os.minor(st_dev))
        os.mknod(devpth, 0400 | stat.S_IFBLK, dev)
    except:
        if util.is_container():
            log.debug("inside container, ignoring mknod failure in resizefs")
            return
        log.warn("Failed to make device node to resize /")
        raise

    cmd = ['blkid', '-c', '/dev/null', '-sTYPE', '-ovalue', devpth]
    try:
        (fstype, _err) = util.subp(cmd)
    except subprocess.CalledProcessError as e:
        log.warn("Failed to get filesystem type of maj=%s, min=%s via: %s" %
            (os.major(st_dev), os.minor(st_dev), cmd))
        log.warn("output=%s\nerror=%s\n", e.output[0], e.output[1])
        os.unlink(devpth)
        raise

    if str(fstype).startswith("ext"):
        resize_cmd = ['resize2fs', devpth]
    elif fstype == "xfs":
        resize_cmd = ['xfs_growfs', devpth]
    else:
        os.unlink(devpth)
        log.debug("not resizing unknown filesystem %s" % fstype)
        return

    if resize_root == "noblock":
        fid = os.fork()
        if fid == 0:
            try:
                do_resize(resize_cmd, devpth, log)
                os._exit(0)  # pylint: disable=W0212
            except Exception as exc:
                sys.stderr.write("Failed: %s" % exc)
                os._exit(1)  # pylint: disable=W0212
    else:
        do_resize(resize_cmd, devpth, log)

    log.debug("resizing root filesystem (type=%s, maj=%i, min=%i, val=%s)" %
        (str(fstype).rstrip("\n"), os.major(st_dev), os.minor(st_dev),
         resize_root))

    return


def do_resize(resize_cmd, devpth, log):
    try:
        start = time.time()
        util.subp(resize_cmd)
    except subprocess.CalledProcessError as e:
        log.warn("Failed to resize filesystem (%s)" % resize_cmd)
        log.warn("output=%s\nerror=%s\n", e.output[0], e.output[1])
        os.unlink(devpth)
        raise

    os.unlink(devpth)
    log.debug("resize took %s seconds" % (time.time() - start))
