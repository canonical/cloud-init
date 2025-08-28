# This file is part of cloud-init. See LICENSE file for license information.

import shutil
import tempfile
import pytest

from cloudinit import util
from tests.unittests.helpers import populate_dir


@pytest.fixture
def tmpdir_path(tmp_path):
    # make a temp directory that gets cleaned up automatically
    return str(tmp_path)


def test_required_only(tmpdir_path):
    dirdata = {"f1": b"f1content", "f2": b"f2content"}
    populate_dir(tmpdir_path, dirdata)

    ret = util.pathprefix2dict(tmpdir_path, required=["f1", "f2"])
    assert dirdata == ret


def test_required_missing(tmpdir_path):
    dirdata = {"f1": b"f1content"}
    populate_dir(tmpdir_path, dirdata)
    kwargs = {"required": ["f1", "f2"]}
    with pytest.raises(ValueError):
        util.pathprefix2dict(tmpdir_path, **kwargs)


def test_no_required_and_optional(tmpdir_path):
    dirdata = {"f1": b"f1c", "f2": b"f2c"}
    populate_dir(tmpdir_path, dirdata)

    ret = util.pathprefix2dict(tmpdir_path, required=None, optional=["f1", "f2"])
    assert dirdata == ret


def test_required_and_optional(tmpdir_path):
    dirdata = {"f1": b"f1c", "f2": b"f2c"}
    populate_dir(tmpdir_path, dirdata)

    ret = util.pathprefix2dict(tmpdir_path, required=["f1"], optional=["f2"])
    assert dirdata == ret
