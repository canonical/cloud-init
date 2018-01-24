# This file is part of cloud-init. See LICENSE file for license information.

import contextlib
import errno
import os
import shutil
import tempfile

_TMPDIR = None
_ROOT_TMPDIR = "/run/cloud-init/tmp"
_EXE_ROOT_TMPDIR = "/var/tmp/cloud-init"


def _tempfile_dir_arg(odir=None, needs_exe=False):
    """Return the proper 'dir' argument for tempfile functions.

    When root, cloud-init will use /run/cloud-init/tmp to avoid
    any cleaning that a distro boot might do on /tmp (such as
    systemd-tmpfiles-clean).

    If the caller of this function (mkdtemp or mkstemp) was provided
    with a 'dir' argument, then that is respected.

    @param odir: original 'dir' arg to 'mkdtemp' or other.
    @param needs_exe: Boolean specifying whether or not exe permissions are
        needed for tempdir. This is needed because /run is mounted noexec.
    """
    if odir is not None:
        return odir

    if needs_exe:
        tdir = _EXE_ROOT_TMPDIR
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
        tdir = os.environ.get('TMPDIR', '/tmp')
    if not os.path.isdir(tdir):
        os.makedirs(tdir)
        os.chmod(tdir, 0o1777)

    _TMPDIR = tdir
    return tdir


def ExtendedTemporaryFile(**kwargs):
    kwargs['dir'] = _tempfile_dir_arg(
        kwargs.pop('dir', None), kwargs.pop('needs_exe', False))
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

    setattr(fh, 'unlink_now', unlink_now)
    return fh


@contextlib.contextmanager
def tempdir(**kwargs):
    # This seems like it was only added in python 3.2
    # Make it since its useful...
    # See: http://bugs.python.org/file12970/tempdir.patch
    tdir = mkdtemp(**kwargs)
    try:
        yield tdir
    finally:
        shutil.rmtree(tdir)


def mkdtemp(**kwargs):
    kwargs['dir'] = _tempfile_dir_arg(
        kwargs.pop('dir', None), kwargs.pop('needs_exe', False))
    return tempfile.mkdtemp(**kwargs)


def mkstemp(**kwargs):
    kwargs['dir'] = _tempfile_dir_arg(
        kwargs.pop('dir', None), kwargs.pop('needs_exe', False))
    return tempfile.mkstemp(**kwargs)

# vi: ts=4 expandtab
