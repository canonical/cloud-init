#!/usr/bin/env python
# Copyright (c) 2012, Cloudscaling
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""cloudinit HACKING file compliance testing (based off of nova hacking.py)

built on top of pep8.py
"""

import inspect
import logging
import re
import sys

import pep8

# Don't need this for testing
logging.disable('LOG')

# N1xx comments
# N2xx except
# N3xx imports
# N4xx docstrings
# N[5-9]XX (future use)

DOCSTRING_TRIPLE = ['"""', "'''"]
VERBOSE_MISSING_IMPORT = False
_missingImport = set([])


def import_normalize(line):
    # convert "from x import y" to "import x.y"
    # handle "from x import y as z" to "import x.y as z"
    split_line = line.split()
    if (line.startswith("from ") and "," not in line and
       split_line[2] == "import" and split_line[3] != "*" and
       split_line[1] != "__future__" and
       (len(split_line) == 4 or (len(split_line) == 6 and
                                 split_line[4] == "as"))):
        return "import %s.%s" % (split_line[1], split_line[3])
    else:
        return line


def cloud_import_alphabetical(physical_line, line_number, lines):
    """Check for imports in alphabetical order.

    HACKING guide recommendation for imports:
    imports in human alphabetical order
    N306
    """
    # handle import x
    # use .lower since capitalization shouldn't dictate order
    split_line = import_normalize(physical_line.strip()).lower().split()
    split_previous = import_normalize(lines[line_number - 2])
    split_previous = split_previous.strip().lower().split()
    # with or without "as y"
    length = [2, 4]
    if (len(split_line) in length and len(split_previous) in length and
            split_line[0] == "import" and split_previous[0] == "import"):
        if split_line[1] < split_previous[1]:
            return (0, "N306: imports not in alphabetical order (%s, %s)"
                    % (split_previous[1], split_line[1]))


def cloud_docstring_start_space(physical_line):
    """Check for docstring not start with space.

    HACKING guide recommendation for docstring:
    Docstring should not start with space
    N401
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    if (pos != -1 and len(physical_line) > pos + 1):
        if (physical_line[pos + 3] == ' '):
            return (pos,
                    "N401: one line docstring should not start with a space")


def cloud_todo_format(physical_line):
    """Check for 'TODO()'.

    HACKING guide recommendation for TODO:
    Include your name with TODOs as in "#TODO(termie)"
    N101
    """
    pos = physical_line.find('TODO')
    pos1 = physical_line.find('TODO(')
    pos2 = physical_line.find('#')  # make sure it's a comment
    if (pos != pos1 and pos2 >= 0 and pos2 < pos):
        return pos, "N101: Use TODO(NAME)"


def cloud_docstring_one_line(physical_line):
    """Check one line docstring end.

    HACKING guide recommendation for one line docstring:
    A one line docstring looks like this and ends in a period.
    N402
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    end = max([physical_line[-4:-1] == i for i in DOCSTRING_TRIPLE])  # end
    if (pos != -1 and end and len(physical_line) > pos + 4):
        if (physical_line[-5] != '.'):
            return pos, "N402: one line docstring needs a period"


def cloud_docstring_multiline_end(physical_line):
    """Check multi line docstring end.

    HACKING guide recommendation for docstring:
    Docstring should end on a new line
    N403
    """
    pos = max([physical_line.find(i) for i in DOCSTRING_TRIPLE])  # start
    if (pos != -1 and len(physical_line) == pos):
        print(physical_line)
        if (physical_line[pos + 3] == ' '):
            return (pos, "N403: multi line docstring end on new line")


current_file = ""


def readlines(filename):
    """Record the current file being tested."""
    pep8.current_file = filename
    return open(filename).readlines()


def add_cloud():
    """Monkey patch pep8 for cloud-init guidelines.

    Look for functions that start with cloud_
    and add them to pep8 module.

    Assumes you know how to write pep8.py checks
    """
    for name, function in globals().items():
        if not inspect.isfunction(function):
            continue
        if name.startswith("cloud_"):
            exec("pep8.%s = %s" % (name, name))


if __name__ == "__main__":
    # NOVA based 'hacking.py' error codes start with an N
    pep8.ERRORCODE_REGEX = re.compile(r'[EWN]\d{3}')
    add_cloud()
    pep8.current_file = current_file
    pep8.readlines = readlines
    try:
        pep8._main()
    finally:
        if len(_missingImport) > 0:
            print >> sys.stderr, ("%i imports missing in this test environment"
                                  % len(_missingImport))

# vi: ts=4 expandtab
