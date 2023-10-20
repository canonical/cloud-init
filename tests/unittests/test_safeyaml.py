# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.safeyaml."""

import pytest

from cloudinit.safeyaml import load_with_marks


class TestLoadWithMarks:
    @pytest.mark.parametrize(
        "source_yaml,loaded_yaml,schemamarks",
        (
            # Invalid cloud-config, non-dict types don't cause an error
            pytest.param(b"scalar", "scalar", {}, id="invalid_nondict_config"),
            pytest.param(
                b"#\na: va\n  \nb: vb\n#\nc: vc",
                {"a": "va", "b": "vb", "c": "vc"},
                {"a": 2, "b": 4, "c": 6},
                id="handle_whitespace_and_comments",
            ),
            pytest.param(
                b"a:\n - a1\n\n - a2\n",
                {"a": ["a1", "a2"]},
                {"a": 1, "a.0": 2, "a.1": 4},
                id="list_items",
            ),
            pytest.param(
                b"a:\n a1:\n\n  aa1: aa1v\n",
                {"a": {"a1": {"aa1": "aa1v"}}},
                {"a": 1, "a.a1": 2, "a.a1.aa1": 4},
                id="nested_dicts_within_dicts",
            ),
            pytest.param(
                b"a:\n- a1\n\n- a2: av2\n  a2b: av2b\n",
                {"a": ["a1", {"a2": "av2", "a2b": "av2b"}]},
                {"a": 1, "a.0": 2, "a.1": 4, "a.1.a2": 4, "a.1.a2b": 5},
                id="nested_dicts_within_list",
            ),
            pytest.param(
                b"[list, of, scalar]",
                ["list", "of", "scalar"],
                {},
                id="list_of_scalar",
            ),
            pytest.param(
                b"{a: [a1, a2], b: [b3]}",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 1, "a.1": 1, "b": 1, "b.0": 1},
                id="dict_of_lists_oneline",
            ),
            pytest.param(
                b"a: [a1, a2]\nb: [b3]",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 1, "a.1": 1, "b": 2, "b.0": 2},
                id="dict_of_lists_multiline",
            ),
            pytest.param(
                b"a:\n- a1\n- a2\nb: [b3]",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 2, "a.1": 3, "b": 4, "b.0": 4},
                id="separate_dicts_scalar_vs_nested_list",
            ),
            pytest.param(
                b"a:\n- a1\n- a2\nb:\n- b3",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 2, "a.1": 3, "b": 4, "b.0": 5},
                id="separate_dicts_nested_lists",
            ),
            pytest.param(
                b"a:\n- {a1: 1}\n- {a2: 2}\n",
                {"a": [{"a1": 1}, {"a2": 2}]},
                {"a": 1, "a.0": 2, "a.0.a1": 2, "a.1": 3, "a.1.a2": 3},
                id="list_of_dict_items",
            ),
            pytest.param(
                b"a:\n- x: ['i', 'ii']\n",
                {"a": [{"x": ["i", "ii"]}]},
                {"a": 1, "a.0": 2, "a.0.x": 2, "a.0.x.0": 2, "a.0.x.1": 2},
                id="list_of_dict_items_with_nested_lists",
            ),
            pytest.param(
                b"a:\n- x: [['i', 'ii']]\n- y: ['iii', 'iv']\n",
                {"a": [{"x": [["i", "ii"]]}, {"y": ["iii", "iv"]}]},
                {
                    "a": 1,
                    "a.0": 2,
                    "a.0.x": 2,
                    "a.0.x.0": 2,
                    "a.0.x.0.0": 2,
                    "a.0.x.0.1": 2,
                    "a.1": 3,
                    "a.1.y": 3,
                    "a.1.y.0": 3,
                    "a.1.y.1": 3,
                },
                id="list_of_dict_items_with_nested_lists_of_lists",
            ),
        ),
    )
    def test_schema_marks_preserved(
        self, source_yaml, loaded_yaml, schemamarks
    ):
        (processed_yaml, yaml_marks) = load_with_marks(source_yaml)
        assert loaded_yaml == processed_yaml
        assert schemamarks == yaml_marks
