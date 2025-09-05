# This file is part of cloud-init. See LICENSE file for license information.

import pytest

from cloudinit import util
from tests.unittests.helpers import populate_dir


class TestPathPrefix2Dict:
    def test_required_only(self, tmp_path):
        dirdata = {"f1": b"f1content", "f2": b"f2content"}
        populate_dir(str(tmp_path), dirdata)

        ret = util.pathprefix2dict(str(tmp_path), required=["f1", "f2"])
        assert dirdata == ret

    def test_required_missing(self, tmp_path):
        dirdata = {"f1": b"f1content"}
        populate_dir(str(tmp_path), dirdata)
        kwargs = {"required": ["f1", "f2"]}
        with pytest.raises(ValueError):
            util.pathprefix2dict(str(tmp_path), **kwargs)

    def test_no_required_and_optional(self, tmp_path):
        dirdata = {"f1": b"f1c", "f2": b"f2c"}
        populate_dir(str(tmp_path), dirdata)

        ret = util.pathprefix2dict(
            str(tmp_path), required=None, optional=["f1", "f2"]
        )
        assert dirdata == ret

    def test_required_and_optional(self, tmp_path):
        dirdata = {"f1": b"f1c", "f2": b"f2c"}
        populate_dir(str(tmp_path), dirdata)

        ret = util.pathprefix2dict(
            str(tmp_path), required=["f1"], optional=["f2"]
        )
        assert dirdata == ret
