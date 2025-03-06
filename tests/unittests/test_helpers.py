# This file is part of cloud-init. See LICENSE file for license information.

"""Tests of the built-in user data handlers."""

import os
from pathlib import Path

import pytest

from cloudinit import sources
from tests.helpers import cloud_init_project_dir, get_top_level_dir
from tests.unittests.helpers import ResourceUsingTestCase, dicts_are_equal


class MyDataSource(sources.DataSource):
    _instance_id = None

    def get_instance_id(self):
        return self._instance_id


class TestPaths(ResourceUsingTestCase):
    def test_get_ipath_and_instance_id_with_slashes(self):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = "/foo/bar"
        safe_iid = "_foo_bar"
        mypaths = self.getCloudPaths(myds)

        self.assertEqual(
            os.path.join(mypaths.cloud_dir, "instances", safe_iid),
            mypaths.get_ipath(),
        )

    def test_get_ipath_and_empty_instance_id_returns_none(self):
        myds = MyDataSource(sys_cfg={}, distro=None, paths={})
        myds._instance_id = None
        mypaths = self.getCloudPaths(myds)

        self.assertIsNone(mypaths.get_ipath())


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


class TestDictsAreEqual:
    """Tests for dicts_are_equal function."""

    def test_identical_dicts(self):
        """Test that identical dicts return True."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "b": 2}
        assert dicts_are_equal(dict1, dict2)

    def test_different_dicts(self):
        """Test that different dicts return False."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "b": 3}
        assert not dicts_are_equal(dict1, dict2)

    def test_different_keys(self):
        """Test that dicts with different keys return False."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "c": 2}
        assert not dicts_are_equal(dict1, dict2)

    def test_different_order_same_content(self):
        """
        Test that dicts with same content but different order return True.
        """
        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 2, "a": 1}
        assert dicts_are_equal(dict1, dict2)

    def test_nested_dicts_equal(self):
        """Test that nested dicts with identical content return True."""
        dict1 = {"a": 1, "b": {"c": 3, "d": 4}}
        dict2 = {"a": 1, "b": {"c": 3, "d": 4}}
        assert dicts_are_equal(dict1, dict2)

    def test_nested_dicts_different(self):
        """Test that nested dicts with different content return False."""
        dict1 = {"a": 1, "b": {"c": 3, "d": 4}}
        dict2 = {"a": 1, "b": {"c": 3, "d": 5}}
        assert not dicts_are_equal(dict1, dict2)

    def test_nested_dict_different_order(self):
        """
        Test that nested dicts with different order & same content return True.
        """
        dict1 = {"a": 1, "b": {"c": 3, "d": 4}}
        dict2 = {"b": {"d": 4, "c": 3}, "a": 1}
        assert dicts_are_equal(dict1, dict2)

    def test_list_values_equal(self):
        """Test that dicts with list values that are identical return True."""
        dict1 = {"a": [1, 2, 3], "b": 2}
        dict2 = {"a": [1, 2, 3], "b": 2}
        assert dicts_are_equal(dict1, dict2)

    def test_list_values_different(self):
        """Test that dicts with list values that are different return False."""
        dict1 = {"a": [1, 2, 3], "b": 2}
        dict2 = {"a": [1, 2, 4], "b": 2}
        assert not dicts_are_equal(dict1, dict2)

    def test_list_order_matters(self):
        """
        Test that dicts with list values in different orders return False.
        """
        dict1 = {"a": [1, 2, 3], "b": 2}
        dict2 = {"a": [3, 2, 1], "b": 2}
        assert not dicts_are_equal(dict1, dict2)

    def test_empty_dicts(self):
        """Test that empty dicts are equal."""
        dict1 = {}
        dict2 = {}
        assert dicts_are_equal(dict1, dict2)

    def test_dict_with_none_values(self):
        """Test dicts containing None values."""
        dict1 = {"a": None, "b": 2}
        dict2 = {"a": None, "b": 2}
        assert dicts_are_equal(dict1, dict2)

    def test_nested_lists_with_dicts(self):
        """Test dicts containing lists of dicts."""
        dict1 = {"a": [{"x": 1}, {"y": 2}]}
        dict2 = {"a": [{"x": 1}, {"y": 2}]}
        assert dicts_are_equal(dict1, dict2)

    def test_nested_lists_with_dicts_different(self):
        """Test dicts containing lists of dicts that differ."""
        dict1 = {"a": [{"x": 1}, {"y": 2}]}
        dict2 = {"a": [{"x": 1}, {"y": 3}]}
        assert not dicts_are_equal(dict1, dict2)

    def test_debug_message_content(self, caplog):
        """Test that debug log contains expected diff content."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "b": 3}

        dicts_are_equal(dict1, dict2)
        # Verify a debug message containing 'Dictionaries do not match' logged
        assert "Dictionaries do not match" in caplog.text

        assert "-b: 2" in caplog.text
        assert "+b: 3" in caplog.text

    @pytest.mark.parametrize(
        "dict1,dict2,expected",
        [
            ({"a": 1}, {"a": 1}, True),
            ({"a": 1}, {"a": 2}, False),
            ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
            ({"a": {"b": 2}}, {"a": {"b": 2}}, True),
            ({"a": {"b": 2}}, {"a": {"b": 3}}, False),
            ({"a": [1, 2]}, {"a": [1, 2]}, True),
            ({"a": [1, 2]}, {"a": [2, 1]}, False),
        ],
    )
    def test_various_dicts(self, dict1, dict2, expected):
        """Parameterized test for multiple dictionary comparisons."""
        assert dicts_are_equal(dict1, dict2) == expected
