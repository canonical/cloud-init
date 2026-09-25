# This file is part of cloud-init. See LICENSE file for license information.

import json
import os
import stat
from unittest import mock

from cloudinit import atomic_helper


class TestAtomicHelper:
    def test_basic_usage(self, tmp_path):
        """write_file takes bytes if no omode."""
        path = tmp_path / "test_basic_usage"
        contents = b"Hey there\n"
        atomic_helper.write_file(path, contents)
        self.check_file(path, contents)

    def test_string(self, tmp_path):
        """write_file can take a string with mode w."""
        path = tmp_path / "test_string"
        contents = "Hey there\n"
        atomic_helper.write_file(path, contents, omode="w")
        self.check_file(path, contents, omode="r")

    def test_file_permissions(self, tmp_path):
        """write_file with mode 400 works correctly."""
        path = tmp_path / "test_file_permissions"
        contents = b"test_file_perms"
        atomic_helper.write_file(path, contents, mode=0o400)
        self.check_file(path, contents, perms=0o400)

    def test_file_preserve_permissions(self, tmp_path):
        """create a file with mode 700, then write_file with mode 644."""
        path = tmp_path / "test_file_preserve_permissions"
        contents = b"test_file_perms"
        with open(path, mode="wb") as f:
            f.write(b"test file preserve permissions")
            os.chmod(f.name, 0o700)
            atomic_helper.write_file(path, contents, preserve_mode=True)
            self.check_file(path, contents, perms=0o700)

    def test_write_json(self, tmp_path):
        """write_json output is readable json."""
        path = tmp_path / "test_write_json"
        data = {"key1": "value1", "key2": ["i1", "i2"]}
        atomic_helper.write_json(path, data)
        with open(path, "r") as fp:
            found = json.load(fp)
        assert data == found
        self.check_perms(path, 0o644)

    def check_file(self, path, content, omode=None, perms=0o644):
        if omode is None:
            omode = "rb"
        assert os.path.exists(path)
        assert os.path.isfile(path)
        with open(path, omode) as fp:
            found = fp.read()
            assert content == found
        self.check_perms(path, perms)

    def check_perms(self, path, perms):
        file_stat = os.stat(path)
        assert perms == stat.S_IMODE(file_stat.st_mode)

    def test_write_file_ensure_dirs(self, tmp_path):
        path = tmp_path / "ensure_dirs" / "ensure/dir"
        contents = b"Hey there\n"
        atomic_helper.write_file(path, contents)
        self.check_file(path, contents)

    def test_write_file_fsyncs(self, tmp_path):
        """write_file flushes and fsyncs the tempfile before renaming."""
        path = tmp_path / "test_write_file_fsyncs"
        contents = b"Hey there\n"
        with mock.patch.object(
            atomic_helper.os, "fsync", return_value=None
        ) as m_fsync:
            atomic_helper.write_file(path, contents)
        assert m_fsync.call_count == 1
        self.check_file(path, contents)

    def test_write_file_fsync_error_is_ignored(self, tmp_path):
        """write_file still succeeds if fsync() raises OSError."""
        path = tmp_path / "test_write_file_fsync_error_is_ignored"
        contents = b"Hey there\n"
        with mock.patch.object(
            atomic_helper.os, "fsync", side_effect=OSError("boom")
        ):
            atomic_helper.write_file(path, contents)
        self.check_file(path, contents)
