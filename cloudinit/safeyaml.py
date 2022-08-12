# Copyright (C) 2012 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from collections import namedtuple
from itertools import chain
from typing import Any, Dict, List, Tuple

import yaml

YAMLError = yaml.YAMLError

# SchemaPathMarks track the path to an element within a loaded YAML file.
# The start_mark and end_mark contain the row and column indicators
# which represent the coordinates where the schema element begins and ends.
SchemaPathMarks = namedtuple(
    "SchemaPathMarks", ("path", "start_mark", "end_mark")
)


class _CustomSafeLoader(yaml.SafeLoader):
    def construct_python_unicode(self, node):
        return super().construct_scalar(node)


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
        self.schemamarks_by_line: Dict[int, List[SchemaPathMarks]] = {}

    def _get_nested_path_prefix(self, node):
        if node.start_mark.line in self.schemamarks_by_line:
            return f"{self.schemamarks_by_line[node.start_mark.line][0][0]}."
        for _line_num, schema_marks in sorted(
            self.schemamarks_by_line.items(), reverse=True
        ):
            for mark in schema_marks[::-1]:
                if (  # Is the node within the scope of the furthest mark
                    node.start_mark.line >= mark.start_mark.line
                    and node.start_mark.column >= mark.start_mark.column
                    and node.end_mark.line <= mark.end_mark.line
                    and node.end_mark.column <= mark.end_mark.column
                ):
                    return f"{mark.path}."
        return ""

    def construct_mapping(self, node):
        mapping = super().construct_mapping(node)
        nested_path_prefix = self._get_nested_path_prefix(node)
        for key_node, value_node in node.value:
            node_key_path = f"{nested_path_prefix}{key_node.value}"
            line_num = key_node.start_mark.line
            mark = SchemaPathMarks(
                node_key_path, key_node.start_mark, value_node.end_mark
            )
            if line_num not in self.schemamarks_by_line:
                self.schemamarks_by_line[line_num] = [mark]
            else:
                self.schemamarks_by_line[line_num].append(mark)
        return mapping

    def construct_sequence(self, node, deep=False):
        sequence = super().construct_sequence(node, deep=True)
        nested_path_prefix = self._get_nested_path_prefix(node)
        for index, sequence_item in enumerate(node.value):
            line_num = sequence_item.start_mark.line
            node_key_path = f"{nested_path_prefix}{index}"
            marks = SchemaPathMarks(
                node_key_path, sequence_item.start_mark, sequence_item.end_mark
            )
            if line_num not in self.schemamarks_by_line:
                self.schemamarks_by_line[line_num] = [marks]
            else:
                self.schemamarks_by_line[line_num].append(marks)
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


_CustomSafeLoader.add_constructor(
    "tag:yaml.org,2002:python/unicode",
    _CustomSafeLoader.construct_python_unicode,
)


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


def load(blob):
    return yaml.load(blob, Loader=_CustomSafeLoader)


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


# vi: ts=4 expandtab
