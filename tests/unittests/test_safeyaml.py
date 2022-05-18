# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.safeyaml."""

import pytest

from cloudinit.safeyaml import load_with_marks


class TestLoadWithMarks:
    @pytest.mark.parametrize(
        "source_yaml,loaded_yaml,schemamarks",
        (
            # Invalid cloud-config, non-dict types don't cause an error
            (b"scalar", "scalar", {}),
            # Multiple keys account for comments and whitespace lines
            (
                b"#\na: va\n  \nb: vb\n#\nc: vc",
                {"a": "va", "b": "vb", "c": "vc"},
                {"a": 2, "b": 4, "c": 6},
            ),
            # List items represented on correct line number
            (
                b"a:\n - a1\n\n - a2\n",
                {"a": ["a1", "a2"]},
                {"a": 1, "a.0": 2, "a.1": 4},
            ),
            # Nested dicts represented on correct line number
            (
                b"a:\n a1:\n\n  aa1: aa1v\n",
                {"a": {"a1": {"aa1": "aa1v"}}},
                {"a": 1, "a.a1": 2, "a.a1.aa1": 4},
            ),
            (b"[list, of, scalar]", ["list", "of", "scalar"], {}),
            (
                b"{a: [a1, a2], b: [b3]}",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 1, "a.1": 1, "b": 1},
            ),
            (
                b"a: [a1, a2]\nb: [b3]",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 1, "a.1": 1, "b": 2, "b.0": 2},
            ),
            (
                b"a:\n- a1\n- a2\nb: [b3]",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 2, "a.1": 3, "b": 4, "b.0": 4},
            ),
            (
                b"a:\n- a1\n- a2\nb:\n- b3",
                {"a": ["a1", "a2"], "b": ["b3"]},
                {"a": 1, "a.0": 2, "a.1": 3, "b": 4, "b.0": 5},
            ),
        ),
    )
    def test_schema_marks_preserved(
        self, source_yaml, loaded_yaml, schemamarks
    ):
        assert (loaded_yaml, schemamarks) == load_with_marks(source_yaml)
