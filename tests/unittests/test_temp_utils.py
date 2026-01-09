# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.temp_utils"""

import os
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
