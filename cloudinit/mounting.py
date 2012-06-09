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
