import builtins
import glob
import os

import pytest

from cloudinit import atomic_helper, util
from tests.unittests.helpers import retarget_many_wrapper

FS_FUNCS = {
    os.path: [
        ("isfile", 1),
        ("exists", 1),
        ("islink", 1),
        ("isdir", 1),
        ("lexists", 1),
        ("relpath", 1),
    ],
    os: [
        ("listdir", 1),
        ("mkdir", 1),
        ("lstat", 1),
        ("symlink", 2),
        ("stat", 1),
        ("scandir", 1),
    ],
    util: [
        ("write_file", 1),
        ("append_file", 1),
        ("load_file", 1),
        ("ensure_dir", 1),
        ("chmod", 1),
        ("delete_dir_contents", 1),
        ("del_file", 1),
        ("sym_link", -1),
        ("copy", -1),
    ],
    glob: [
        ("glob", 1),
    ],
    builtins: [
        ("open", 1),
    ],
    atomic_helper: [
        ("write_file", 1),
    ],
}


@pytest.fixture
def fake_filesystem(mocker, tmpdir):
    """Mocks fs functions to operate under `tmpdir`"""
    for (mod, funcs) in FS_FUNCS.items():
        for f, nargs in funcs:
            func = getattr(mod, f)
            trap_func = retarget_many_wrapper(str(tmpdir), nargs, func)
            mocker.patch.object(mod, f, trap_func)
