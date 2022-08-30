# This file is part of cloud-init. See LICENSE file for license information.

import contextlib
import errno
import os
import shutil
import tempfile

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)
_TMPDIR = None
_ROOT_TMPDIR = "/run/cloud-init/tmp"
_EXE_ROOT_TMPDIR = "/var/tmp/cloud-init"


def _is_noexec_mount(path) -> bool:
    *_, mnt_opts = util.get_mount_info(path, get_mnt_opts=True)
    return "noexec" in mnt_opts


def _tempfile_dir_arg(odir=None, needs_exe: bool = False, alt_exe_dir=None):
    """Return the proper 'dir' argument for tempfile functions.

    When root, cloud-init will use /run/cloud-init/tmp to avoid
    any cleaning that a distro boot might do on /tmp (such as
    systemd-tmpfiles-clean).

    If the caller of this function (mkdtemp or mkstemp) was provided
    with a 'dir' argument, then that is respected.

    @param odir: original 'dir' arg to 'mkdtemp' or other.
    @param needs_exe: Boolean specifying whether or not exe permissions are
        needed for tempdir. This is needed because /run is mounted noexec.
    @param alt_exe_dir: Alternative dir with exec permission.
    """
    if odir is not None:
        return odir

    if needs_exe:
        tdir = _EXE_ROOT_TMPDIR
        if _is_noexec_mount(tdir):
            msg = (
                f"Requested temporal dir with exe permission `{tdir}` is"
                " mounted as noexec"
            )
            if alt_exe_dir:
                msg += f". Falling back to `{alt_exe_dir}`"
                tdir = alt_exe_dir
            LOG.debug(msg)
        if not os.path.isdir(tdir):
            os.makedirs(tdir)
            os.chmod(tdir, 0o1777)
        return tdir

    global _TMPDIR
    if _TMPDIR:
        return _TMPDIR

    if os.getuid() == 0:
        tdir = _ROOT_TMPDIR
    else:
        tdir = os.environ.get("TMPDIR", "/tmp")
    if not os.path.isdir(tdir):
        os.makedirs(tdir)
        os.chmod(tdir, 0o1777)

    _TMPDIR = tdir
    return tdir


def ExtendedTemporaryFile(**kwargs):
    kwargs["dir"] = _tempfile_dir_arg(
        kwargs.pop("dir", None), kwargs.pop("needs_exe", False)
    )
    fh = tempfile.NamedTemporaryFile(**kwargs)
    # Replace its unlink with a quiet version
    # that does not raise errors when the
    # file to unlink has been unlinked elsewhere..

    def _unlink_if_exists(path):
        try:
            os.unlink(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise e

    fh.unlink = _unlink_if_exists

    # Add a new method that will unlink
    # right 'now' but still lets the exit
    # method attempt to remove it (which will
    # not throw due to our del file being quiet
    # about files that are not there)
    def unlink_now():
        fh.unlink(fh.name)

    setattr(fh, "unlink_now", unlink_now)
    return fh


@contextlib.contextmanager
def tempdir(rmtree_ignore_errors=False, **kwargs):
    # This seems like it was only added in python 3.2
    # Make it since its useful...
    # See: http://bugs.python.org/file12970/tempdir.patch
    tdir = mkdtemp(**kwargs)
    try:
        yield tdir
    finally:
        shutil.rmtree(tdir, ignore_errors=rmtree_ignore_errors)


def mkdtemp(dir=None, needs_exe: bool = False, alt_exe_dir=None, **kwargs):
    dir = _tempfile_dir_arg(dir, needs_exe, alt_exe_dir)
    return tempfile.mkdtemp(dir=dir, **kwargs)


def mkstemp(dir=None, needs_exe: bool = False, alt_exe_dir=None, **kwargs):
    dir = _tempfile_dir_arg(dir, needs_exe, alt_exe_dir)
    return tempfile.mkstemp(dir=dir, **kwargs)


# vi: ts=4 expandtab
