# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.temp_utils"""

import os
import stat
from tempfile import gettempdir

import pytest

from cloudinit.temp_utils import mkdtemp, mkstemp, tempdir
from tests.unittests.helpers import wrap_and_call


class TestTempUtils:
    prefix = gettempdir()

    def test_mkdtemp_default_non_root(self):
        """mkdtemp creates a dir under /tmp for the unprivileged."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return "/fake/return/path"

        retval = wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.getuid": 1000,
                "tempfile.mkdtemp": {"side_effect": fake_mkdtemp},
                "os.path.isdir": True,
            },
            mkdtemp,
        )
        assert "/fake/return/path" == retval
        assert os.path.abspath(self.prefix) == os.path.abspath(
            calls.pop(0).get("dir", "")
        )

    def test_mkdtemp_default_non_root_needs_exe(self):
        """mkdtemp creates a dir under /var/tmp/cloud-init when needs_exe."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return "/fake/return/path"

        retval = wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.getuid": 1000,
                "tempfile.mkdtemp": {"side_effect": fake_mkdtemp},
                "os.path.isdir": True,
                "util.has_mount_opt": True,
            },
            mkdtemp,
            needs_exe=True,
        )
        assert "/fake/return/path" == retval
        assert [{"dir": "/var/tmp/cloud-init"}] == calls

    def test_mkdtemp_default_root(self):
        """mkdtemp creates a dir under /run/cloud-init for the privileged."""
        calls = []

        def fake_mkdtemp(*args, **kwargs):
            calls.append(kwargs)
            return "/fake/return/path"

        retval = wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.getuid": 0,
                "tempfile.mkdtemp": {"side_effect": fake_mkdtemp},
                "os.path.isdir": True,
            },
            mkdtemp,
        )
        assert "/fake/return/path" == retval
        assert [{"dir": "/run/cloud-init/tmp"}] == calls

    def test_mkstemp_default_non_root(self):
        """mkstemp creates secure tempfile under /tmp for the unprivileged."""
        calls = []

        def fake_mkstemp(*args, **kwargs):
            calls.append(kwargs)
            return "/fake/return/path"

        retval = wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.getuid": 1000,
                "tempfile.mkstemp": {"side_effect": fake_mkstemp},
                "os.path.isdir": True,
            },
            mkstemp,
        )
        assert "/fake/return/path" == retval
        assert os.path.abspath(self.prefix) == os.path.abspath(
            calls.pop(0).get("dir", "")
        )

    def test_mkstemp_default_root(self):
        """mkstemp creates a secure tempfile in /run/cloud-init for root."""
        calls = []

        def fake_mkstemp(*args, **kwargs):
            calls.append(kwargs)
            return "/fake/return/path"

        retval = wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.getuid": 0,
                "tempfile.mkstemp": {"side_effect": fake_mkstemp},
                "os.path.isdir": True,
            },
            mkstemp,
        )
        assert "/fake/return/path" == retval
        assert [{"dir": "/run/cloud-init/tmp"}] == calls

    def test_mkdtemp_creates_missing_ancestor_not_world_writable(
        self, tmp_path
    ):
        """mkdtemp creates missing ancestor dirs with mode 0o700 (GH-4189)."""
        ancestor = str(tmp_path / "scratch")
        retval = mkdtemp(dir=ancestor)
        assert os.path.isdir(retval)
        assert 0o700 == stat.S_IMODE(os.stat(ancestor).st_mode)

    def test_mkstemp_creates_missing_ancestor_not_world_writable(
        self, tmp_path
    ):
        """mkstemp creates missing ancestor dirs with mode 0o700 (GH-4189)."""
        ancestor = str(tmp_path / "scratch")
        fd, retval = mkstemp(dir=ancestor)
        os.close(fd)
        assert os.path.isfile(retval)
        assert 0o700 == stat.S_IMODE(os.stat(ancestor).st_mode)

    @pytest.mark.parametrize("system_tmpdir", ["/tmp", "/var/tmp"])
    def test_system_tmp_dirs_keep_sticky_world_writable_mode(
        self, system_tmpdir
    ):
        """/tmp and /var/tmp stay 1777 if cloud-init creates them (GH-4189).

        cloud-init can be the creator of these shared directories when it
        runs before systemd-tmpfiles-setup.service.
        """
        chmod_calls = []

        def fake_chmod(*args):
            chmod_calls.append(args)

        wrap_and_call(
            "cloudinit.temp_utils",
            {
                "os.path.isdir": False,
                "os.makedirs": {"return_value": None},
                "os.chmod": {"side_effect": fake_chmod},
                "tempfile.mkdtemp": {"return_value": "/fake/return/path"},
            },
            mkdtemp,
            dir=system_tmpdir,
        )
        assert [(system_tmpdir, 0o1777)] == chmod_calls

    def test_tempdir_error_suppression(self):
        """test tempdir suppresses errors during directory removal."""

        with pytest.raises(OSError):
            with tempdir(prefix="cloud-init-dhcp-") as tdir:
                os.rmdir(tdir)
                # As a result, the directory is already gone,
                # so shutil.rmtree should raise OSError

        with tempdir(
            rmtree_ignore_errors=True, prefix="cloud-init-dhcp-"
        ) as tdir:
            os.rmdir(tdir)
            # Since the directory is already gone, shutil.rmtree would raise
            # OSError, but we suppress that
