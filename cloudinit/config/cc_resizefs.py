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

import os
import stat
import time

from cloudinit.settings import PER_ALWAYS
from cloudinit import util

frequency = PER_ALWAYS

RESIZE_FS_PREFIXES_CMDS = [
    ('ext', 'resize2fs'),
    ('xfs', 'xfs_growfs'),
]


def nodeify_path(devpth, where, log):
    try:
        st_dev = os.stat(where).st_dev
        dev = os.makedev(os.major(st_dev), os.minor(st_dev))
        os.mknod(devpth, 0400 | stat.S_IFBLK, dev)
        return st_dev
    except:
        if util.is_container():
            log.debug("Inside container, ignoring mknod failure in resizefs")
            return
        log.warn("Failed to make device node to resize %s at %s",
                 where, devpth)
        raise


def get_fs_type(st_dev, path, log):
    try:
        dev_entries = util.find_devs_with(tag='TYPE', oformat='value',
                                         no_cache=True, path=path)
        if not dev_entries:
            return None
        return dev_entries[0].strip()
    except util.ProcessExecutionError:
        util.logexc(log, ("Failed to get filesystem type"
                          " of maj=%s, min=%s for path %s"),
                    os.major(st_dev), os.minor(st_dev), path)
        raise


def handle(name, cfg, _cloud, log, args):
    if len(args) != 0:
        resize_root = args[0]
    else:
        resize_root = util.get_cfg_option_str(cfg, "resize_rootfs", True)

    if not util.translate_bool(resize_root):
        log.debug("Skipping module named %s, resizing disabled", name)
        return

    # TODO(harlowja) is the directory ok to be used??
    resize_root_d = util.get_cfg_option_str(cfg, "resize_rootfs_tmp", "/run")
    util.ensure_dir(resize_root_d)

    # TODO(harlowja): allow what is to be resized to be configurable??
    resize_what = "/"
    with util.ExtendedTemporaryFile(prefix="cloudinit.resizefs.",
                                    dir=resize_root_d, delete=True) as tfh:
        devpth = tfh.name

        # Delete the file so that mknod will work
        # but don't change the file handle to know that its
        # removed so that when a later call that recreates
        # occurs this temporary file will still benefit from
        # auto deletion
        tfh.unlink_now()

        st_dev = nodeify_path(devpth, resize_what, log)
        fs_type = get_fs_type(st_dev, devpth, log)
        if not fs_type:
            log.warn("Could not determine filesystem type of %s", resize_what)
            return

        resizer = None
        fstype_lc = fs_type.lower()
        for (pfix, root_cmd) in RESIZE_FS_PREFIXES_CMDS:
            if fstype_lc.startswith(pfix):
                resizer = root_cmd
                break

        if not resizer:
            log.warn("Not resizing unknown filesystem type %s for %s",
                     fs_type, resize_what)
            return

        log.debug("Resizing %s (%s) using %s", resize_what, fs_type, resizer)
        resize_cmd = [resizer, devpth]

        if resize_root == "noblock":
            # Fork to a child that will run
            # the resize command
            util.fork_cb(do_resize, resize_cmd, log)
            # Don't delete the file now in the parent
            tfh.delete = False
        else:
            do_resize(resize_cmd, log)

    action = 'Resized'
    if resize_root == "noblock":
        action = 'Resizing (via forking)'
    log.debug("%s root filesystem (type=%s, maj=%i, min=%i, val=%s)",
              action, fs_type, os.major(st_dev), os.minor(st_dev), resize_root)


def do_resize(resize_cmd, log):
    start = time.time()
    try:
        util.subp(resize_cmd)
    except util.ProcessExecutionError:
        util.logexc(log, "Failed to resize filesystem (cmd=%s)", resize_cmd)
        raise
    tot_time = time.time() - start
    log.debug("Resizing took %.3f seconds", tot_time)
    # TODO(harlowja): Should we add a fsck check after this to make
    # sure we didn't corrupt anything?
