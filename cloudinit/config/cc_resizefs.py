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


def _resize_btrfs(mount_point, devpth):  # pylint: disable=W0613
    return ('btrfs', 'filesystem', 'resize', 'max', mount_point)


def _resize_ext(mount_point, devpth):  # pylint: disable=W0613
    return ('resize2fs', devpth)


def _resize_xfs(mount_point, devpth):  # pylint: disable=W0613
    return ('xfs_growfs', devpth)

# Do not use a dictionary as these commands should be able to be used
# for multiple filesystem types if possible, e.g. one command for
# ext2, ext3 and ext4.
RESIZE_FS_PREFIXES_CMDS = [
    ('btrfs', _resize_btrfs),
    ('ext', _resize_ext),
    ('xfs', _resize_xfs),
]

NOBLOCK = "noblock"


def get_mount_info(path, log):
    # Use /proc/$$/mountinfo to find the device where path is mounted.
    # This is done because with a btrfs filesystem using os.stat(path)
    # does not return the ID of the device.
    #
    # Here, / has a device of 18 (decimal).
    #
    # $ stat /
    #   File: '/'
    #   Size: 234               Blocks: 0          IO Block: 4096   directory
    # Device: 12h/18d   Inode: 256         Links: 1
    # Access: (0755/drwxr-xr-x)  Uid: (    0/    root)   Gid: (    0/    root)
    # Access: 2013-01-13 07:31:04.358011255 +0000
    # Modify: 2013-01-13 18:48:25.930011255 +0000
    # Change: 2013-01-13 18:48:25.930011255 +0000
    #  Birth: -
    #
    # Find where / is mounted:
    #
    # $ mount | grep ' / '
    # /dev/vda1 on / type btrfs (rw,subvol=@,compress=lzo)
    #
    # And the device ID for /dev/vda1 is not 18:
    #
    # $ ls -l /dev/vda1
    # brw-rw---- 1 root disk 253, 1 Jan 13 08:29 /dev/vda1
    #
    # So use /proc/$$/mountinfo to find the device underlying the
    # input path.
    path_elements = [e for e in path.split('/') if e]
    devpth = None
    fs_type = None
    match_mount_point = None
    match_mount_point_elements = None
    mountinfo_path = '/proc/%s/mountinfo' % os.getpid()
    for line in util.load_file(mountinfo_path).splitlines():
        parts = line.split()

        mount_point = parts[4]
        mount_point_elements = [e for e in mount_point.split('/') if e]

        # Ignore mounts deeper than the path in question.
        if len(mount_point_elements) > len(path_elements):
            continue

        # Ignore mounts where the common path is not the same.
        l = min(len(mount_point_elements), len(path_elements))
        if mount_point_elements[0:l] != path_elements[0:l]:
            continue

        # Ignore mount points higher than an already seen mount
        # point.
        if (match_mount_point_elements is not None and
            len(match_mount_point_elements) > len(mount_point_elements)):
            continue

        # Find the '-' which terminates a list of optional columns to
        # find the filesystem type and the path to the device.  See
        # man 5 proc for the format of this file.
        try:
            i = parts.index('-')
        except ValueError:
            log.debug("Did not find column named '-' in %s",
                      mountinfo_path)
            return None

        # Get the path to the device.
        try:
            fs_type = parts[i + 1]
            devpth = parts[i + 2]
        except IndexError:
            log.debug("Too few columns in %s after '-' column", mountinfo_path)
            return None

        match_mount_point = mount_point
        match_mount_point_elements = mount_point_elements

    if devpth and fs_type and match_mount_point:
        return (devpth, fs_type, match_mount_point)
    else:
        return None


def handle(name, cfg, _cloud, log, args):
    if len(args) != 0:
        resize_root = args[0]
    else:
        resize_root = util.get_cfg_option_str(cfg, "resize_rootfs", True)

    if not util.translate_bool(resize_root, addons=[NOBLOCK]):
        log.debug("Skipping module named %s, resizing disabled", name)
        return

    # TODO(harlowja) is the directory ok to be used??
    resize_root_d = util.get_cfg_option_str(cfg, "resize_rootfs_tmp", "/run")
    util.ensure_dir(resize_root_d)

    # TODO(harlowja): allow what is to be resized to be configurable??
    resize_what = "/"
    result = get_mount_info(resize_what, log)
    if not result:
        log.warn("Could not determine filesystem type of %s", resize_what)
        return

    (devpth, fs_type, mount_point) = result

    # Ensure the path is a block device.
    if not stat.S_ISBLK(os.stat(devpth).st_mode):
        log.debug("The %s device which was found for mount point %s for %s "
                  "is not a block device" % (devpth, mount_point, resize_what))
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

    resize_cmd = resizer(resize_what, devpth)
    log.debug("Resizing %s (%s) using %s", resize_what, fs_type,
              ' '.join(resize_cmd))

    if resize_root == NOBLOCK:
        # Fork to a child that will run
        # the resize command
        util.fork_cb(do_resize, resize_cmd, log)
    else:
        do_resize(resize_cmd, log)

    action = 'Resized'
    if resize_root == NOBLOCK:
        action = 'Resizing (via forking)'
    log.debug("%s root filesystem (type=%s, val=%s)", action, fs_type,
              resize_root)


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
