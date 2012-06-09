# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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

import contextlib

from cloudinit import util


class MountFailedError(Exception):
    pass


@contextlib.contextmanager
def unmounter(umount):
    try:
        yield umount
    finally:
        if umount:
            sh.subp(["umount", '-l', umount])


def mount_callback_umount(device, callback, data=None):
    """
    mount the device, call method 'callback' passing the directory
    in which it was mounted, then unmount.  Return whatever 'callback'
    returned.  If data != None, also pass data to callback.
    """

    # go through mounts to see if it was already mounted
    mounts = sh.load_file("/proc/mounts").splitlines()
    mounted = {}
    for mpline in mounts:
        (dev, mp, fstype, _opts, _freq, _passno) = mpline.split()
        mp = mp.replace("\\040", " ")
        mounted[dev] = (dev, fstype, mp, False)

    with util.tempdir() as tmpd:
        umount = False
        if device in mounted:
            mountpoint = "%s/" % mounted[device][2]
        else:
            try:
                mountcmd = ["mount", "-o", "ro", device, tmpd]
                util.subp(mountcmd)
                umount = tmpd
            except IOError as exc:
                raise MountFailedError("%s" % (exc))
            mountpoint = "%s/" % tmpd
        with unmounter(umount):
            if data is None:
                ret = callback(mountpoint)
            else:
                ret = callback(mountpoint, data)
            return ret
