# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os
from pathlib import Path

import pytest

from cloudinit import sources
from cloudinit.helpers import DefaultingConfigParser
from tests.helpers import cloud_init_project_dir, get_top_level_dir


class MyDataSource(sources.DataSource):
    _instance_id = None

    def get_instance_id(self):
        return self._instance_id


class TestPaths:
    def test_get_ipath_and_instance_id_with_slashes(self, paths):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = "/foo/bar"
        paths.datasource = myds
        safe_iid = "_foo_bar"

        assert (
            os.path.join(paths.cloud_dir, "instances", safe_iid)
            == paths.get_ipath()
        )

    def test_get_ipath_and_empty_instance_id_returns_none(self, paths):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = None
        paths.datasource = myds

        assert paths.get_ipath() is None


class Testcloud_init_project_dir:
    top_dir = get_top_level_dir()

    @staticmethod
    def _get_top_level_dir_alt_implementation():
        """Alternative implementation for comparing against.

        Note: Recursively searching for .git/ fails during build tests due to
        .git not existing. This implementation assumes that ../../../ is the
        relative path to the cloud-init project directory form this file.
        """
        out = Path(__file__).parent.parent.parent.resolve()
        return out

    def test_top_level_dir(self):
        """Assert the location of the top project directory is correct"""
        assert self.top_dir == self._get_top_level_dir_alt_implementation()

    def test_cloud_init_project_dir(self):
        """Assert cloud_init_project_dir produces an expected location

        Compare the returned value to an alternate (naive) implementation
        """
        assert (
            str(Path(self.top_dir, "test"))
            == cloud_init_project_dir("test")
            == str(Path(self._get_top_level_dir_alt_implementation(), "test"))
        )


class TestDefaultingConfigParser:
    def test_get_or_default(self) -> None:
        parser = DefaultingConfigParser()
        parser.read_string("""[section1]
            option1 = value1
""")

        assert parser.get_or_default("section1", "option1") == "value1"
        assert parser.get_or_default("missing_section", "option1") is None
        assert parser.get_or_default("section1", "missing_option") is None

    def test_getboolean_or_default(self) -> None:
        parser = DefaultingConfigParser()
        parser.read_string("""[section1]
            enabled = yes
            disabled = no
            invalid = ab
        """)

        assert parser.getboolean_or_default("section1", "enabled") is True
        assert parser.getboolean_or_default("section1", "disabled") is False
        assert parser.getboolean_or_default("missing_sec", "enabled") is False
        assert parser.getboolean_or_default("section1", "missing_opt") is False

        with pytest.raises(ValueError):
            parser.getboolean_or_default("section1", "invalid")

    def test_getfloat_or_default(self) -> None:
        parser = DefaultingConfigParser()
        parser.read_string("""[section1]
            valid = 1.25
            invalid = ab
        """)

        assert parser.getfloat_or_default("section1", "valid") == 1.25
        assert parser.getfloat_or_default("missing", "valid") == 0.0
        assert parser.getfloat_or_default("section1", "missing_opt") == 0.0

        with pytest.raises(ValueError):
            parser.getfloat_or_default("section1", "invalid")

    def test_getint_or_default(self) -> None:
        parser = DefaultingConfigParser()
        parser.read_string("""[section1]
            valid = 5
            invalid = ab
        """)

        assert parser.getint_or_default("section1", "valid") == 5
        assert parser.getint_or_default("missing_sec", "valid") == 0
        assert parser.getint_or_default("section1", "missing_opt") == 0

        with pytest.raises(ValueError):
            parser.getint_or_default("section1", "invalid")
