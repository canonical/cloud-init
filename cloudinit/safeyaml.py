# Copyright (C) 2012 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from collections import defaultdict
from itertools import chain
from typing import Any, Dict, List, Tuple

import yaml


# SchemaPathMarks track the path to an element within a loaded YAML file.
# The start_mark and end_mark contain the row and column indicators
# which represent the coordinates where the schema element begins and ends.
class SchemaPathMarks:
    def __init__(self, path: str, start_mark: yaml.Mark, end_mark: yaml.Mark):
        self.path = path
        self.start_mark = start_mark
        self.end_mark = end_mark

    def __contains__(self, other):
        """Return whether other start/end marks are within self marks."""
        if (
            other.start_mark.line < self.start_mark.line
            or other.end_mark.line > self.end_mark.line
        ):
            return False
        if (
            other.start_mark.line == self.start_mark.line
            and other.start_mark.column < self.start_mark.column
        ):
            return False
        if (
            other.end_mark.line == self.end_mark.line
            and other.end_mark.column > self.end_mark.column
        ):
            return False
        return True

    def __eq__(self, other):
        return (
            self.start_mark.line == other.start_mark.line
            and self.start_mark.column == other.start_mark.column
            and self.end_mark.line == other.end_mark.line
            and self.end_mark.column == other.end_mark.column
        )


def _find_closest_parent(child_mark, marks):
    for mark in marks[::-1]:
        if child_mark in mark and not child_mark == mark:
            return mark
    return None


def _reparent_schema_mark_children(line_marks: List[SchemaPathMarks]):
    """
    Update any SchemaPathMarks.path for items not under the proper parent.
    """
    for mark in line_marks:
        parent = _find_closest_parent(mark, line_marks)
        if parent:
            path_prefix, _path_idx = mark.path.rsplit(".", 1)
            if mark.path == parent.path or not mark.path.startswith(
                parent.path
            ):
                # Reparent, replacing only the first match of path_prefix
                mark.path = mark.path.replace(path_prefix, parent.path, 1)


def _add_mark_and_reparent_marks(
    new_mark: SchemaPathMarks, marks: List[SchemaPathMarks]
) -> List[SchemaPathMarks]:
    """Insert new_mark into marks, ordering ancestors first.

    Reparent existing SchemaPathMarks.path when new_mark is a parent of
    an existing mark item.

    Because schema processing is depth first, leaf/child mappings and
    sequences may be processed for SchemaPathMarks before their parents.
    This leads to SchemaPathMarks.path of 'grandchildren' being incorrectly
    parented by the root dictionary instead of an intermediary parents below
    root.

    Walk through the list of existing marks and reparent marks that are
    contained within the new_mark.
    """
    new_marks = []
    reparent_paths = False
    for mark in marks:
        if mark not in new_mark:
            new_marks.append(mark)
            continue
        if new_mark not in new_marks:
            reparent_paths = True
            # Insert new_mark first as it is a parent of mark
            new_marks.append(new_mark)
        new_marks.append(mark)
    if reparent_paths:
        _reparent_schema_mark_children(new_marks)
    else:
        new_marks.append(new_mark)
    return new_marks


class _CustomSafeLoaderWithMarks(yaml.SafeLoader):
    """A loader which provides line and column start and end marks for YAML.

    If the YAML loaded represents a dictionary, get_single_data will inject
    a top-level "schemamarks" key in that dictionary which can be used at
    call-sites to process YAML paths schemamark metadata when annotating
    YAML files for errors.

    The schemamarks key is dictionary where each key is a dot-delimited path
    into the YAML object. Each dot represents an element that is nested under
    a parent and list items are represented with the format
    `<parent>.<list-index>`.

    The values in schemamarks will be the line number in the original content
    where YAML element begins to aid in annotation when encountering schema
    errors.

    The example YAML shows expected schemamarks for both dicts and lists:

      one: val1
      two:
        subtwo: val2
      three: [val3, val4]

    schemamarks == {
        "one": 1, "two": 2, "two.subtwo": 3, "three": 4, "three.0": 4,
        "three.1": 4
    }
    """

    def __init__(self, stream):
        super().__init__(stream)
        self.schemamarks_by_line: Dict[int, List[SchemaPathMarks]] = (
            defaultdict(list)
        )

    def _get_nested_path_prefix(self, node):
        if node.start_mark.line in self.schemamarks_by_line:
            # Find most specific match
            most_specific_mark = self.schemamarks_by_line[
                node.start_mark.line
            ][0]
            for path_mark in self.schemamarks_by_line[node.start_mark.line][
                1:
            ]:
                if node in path_mark and path_mark in most_specific_mark:
                    most_specific_mark = path_mark
            if node in most_specific_mark:
                return most_specific_mark.path + "."
        for _line_num, schema_marks in sorted(
            self.schemamarks_by_line.items(), reverse=True
        ):
            for mark in schema_marks[::-1]:
                if node in mark:
                    return f"{mark.path}."
        return ""

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        nested_path_prefix = self._get_nested_path_prefix(node)
        for key_node, value_node in node.value:
            node_key_path = f"{nested_path_prefix}{key_node.value}"
            line_num = key_node.start_mark.line
            new_mark = SchemaPathMarks(
                node_key_path, key_node.start_mark, value_node.end_mark
            )
            schema_marks = self.schemamarks_by_line[line_num]
            new_marks = _add_mark_and_reparent_marks(new_mark, schema_marks)
            self.schemamarks_by_line[line_num] = new_marks
        return mapping

    def construct_sequence(self, node, deep=False):
        sequence = super().construct_sequence(node, deep=True)
        nested_path_prefix = self._get_nested_path_prefix(node)
        for index, sequence_item in enumerate(node.value):
            line_num = sequence_item.start_mark.line
            node_key_path = f"{nested_path_prefix}{index}"
            new_mark = SchemaPathMarks(
                node_key_path, sequence_item.start_mark, sequence_item.end_mark
            )
            if line_num not in self.schemamarks_by_line:
                self.schemamarks_by_line[line_num] = [new_mark]
            else:
                if line_num == sequence_item.end_mark.line:
                    schema_marks = self.schemamarks_by_line[line_num]
                    new_marks = _add_mark_and_reparent_marks(
                        new_mark, schema_marks
                    )
                    self.schemamarks_by_line[line_num] = new_marks
                else:  # Incorrect multi-line mapping or sequence object.
                    for inner_line in range(
                        line_num, sequence_item.end_mark.line
                    ):
                        if inner_line in self.schemamarks_by_line:
                            schema_marks = self.schemamarks_by_line[inner_line]
                            new_marks = _add_mark_and_reparent_marks(
                                new_mark, schema_marks
                            )
                            if (
                                inner_line == line_num
                                and schema_marks[0].path != node_key_path
                            ):
                                new_marks.insert(
                                    0,
                                    SchemaPathMarks(
                                        node_key_path,
                                        schema_marks[0].start_mark,
                                        schema_marks[-1].end_mark,
                                    ),
                                )
                            self.schemamarks_by_line[inner_line] = new_marks
        return sequence

    def get_single_data(self):
        data = super().get_single_data()
        if isinstance(data, dict):  # valid cloud-config schema is a dict
            data["schemamarks"] = dict(
                [
                    (v.path, v.start_mark.line + 1)  # 1-based human-readable
                    for v in chain(*self.schemamarks_by_line.values())
                ]
            )
        return data


class NoAliasSafeDumper(yaml.dumper.SafeDumper):
    """A class which avoids constructing anchors/aliases on yaml dump"""

    def ignore_aliases(self, data):
        return True


def load_with_marks(blob) -> Tuple[Any, Dict[str, int]]:
    """Perform YAML SafeLoad and track start and end marks during parse.

    JSON schema errors come with an encoded object path such as:
        <key1>.<key2>.<list_item_index>

    YAML loader needs to preserve a mapping of schema path to line and column
    marks to annotate original content with JSON schema error marks for the
    command:
        cloud-init devel schema --annotate


    """
    result = yaml.load(blob, Loader=_CustomSafeLoaderWithMarks)
    if not isinstance(result, dict):
        schemamarks = {}
    else:
        schemamarks = result.pop("schemamarks")
    return result, schemamarks


def dumps(obj, explicit_start=True, explicit_end=True, noalias=False):
    """Return data in nicely formatted yaml."""

    return yaml.dump(
        obj,
        line_break="\n",
        indent=4,
        explicit_start=explicit_start,
        explicit_end=explicit_end,
        default_flow_style=False,
        Dumper=(NoAliasSafeDumper if noalias else yaml.dumper.SafeDumper),
    )
