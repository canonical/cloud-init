# This file is part of cloud-init. See LICENSE file for license information.

import contextlib
import errno
import logging
import os
import shutil
import tempfile
from typing import Any, Iterator, Optional, Tuple, cast

from cloudinit import util

LOG = logging.getLogger(__name__)
_ROOT_TMPDIR = "/run/cloud-init/tmp"
_EXE_ROOT_TMPDIR = "/var/tmp/cloud-init"


def get_tmp_ancestor(
    odir: Optional[str] = None, needs_exe: bool = False
) -> str:
    if odir is not None:
        return odir
    if needs_exe:
        return _EXE_ROOT_TMPDIR
    if os.getuid() == 0:
        if util.is_BSD():
            return "/var/" + _ROOT_TMPDIR
        else:
            return _ROOT_TMPDIR
    return os.environ.get("TMPDIR", "/tmp")


def _tempfile_dir_arg(
    odir: Optional[str] = None, needs_exe: bool = False
) -> str:
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
    tdir = get_tmp_ancestor(odir, needs_exe)
    if not os.path.isdir(tdir):
        os.makedirs(tdir)
        os.chmod(tdir, 0o1777)

    if needs_exe:
        if util.has_mount_opt(tdir, "noexec"):
            LOG.warning(
                "Requested temporal dir with exe permission `%s` is"
                " mounted as noexec",
                tdir,
            )
    return tdir


class _ExtendedTemporaryFile(tempfile._TemporaryFileWrapper):
    def unlink(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise e

    def unlink_now(self) -> None:
        self.unlink(self.name)


def ExtendedTemporaryFile(**kwargs: Any) -> _ExtendedTemporaryFile:
    kwargs["dir"] = _tempfile_dir_arg()
    fh = tempfile.NamedTemporaryFile(**kwargs)
    # NamedTemporaryFile is a factory function that always builds a
    # plain _TemporaryFileWrapper internally, so we can't construct
    # our subclass directly. Reassigning __class__ after the fact is
    # the standard way to extend it without depending on tempfile's
    # private construction internals. mypy can't see this runtime
    # class change, so we cast() to tell it the true resulting type.
    fh.__class__ = _ExtendedTemporaryFile
    return cast(_ExtendedTemporaryFile, fh)


@contextlib.contextmanager
def tempdir(
    rmtree_ignore_errors: bool = False, **kwargs: Any
) -> Iterator[str]:
    # This seems like it was only added in python 3.2
    # Make it since its useful...
    # See: http://bugs.python.org/file12970/tempdir.patch
    tdir = mkdtemp(**kwargs)
    try:
        yield tdir
    finally:
        shutil.rmtree(tdir, ignore_errors=rmtree_ignore_errors)


def mkdtemp(
    dir: Optional[str] = None, needs_exe: bool = False, **kwargs: Any
) -> str:
    dir = _tempfile_dir_arg(dir, needs_exe)
    return tempfile.mkdtemp(dir=dir, **kwargs)


def mkstemp(
    dir: Optional[str] = None, needs_exe: bool = False, **kwargs: Any
) -> Tuple[int, str]:
    dir = _tempfile_dir_arg(dir, needs_exe)
    return tempfile.mkstemp(dir=dir, **kwargs)
