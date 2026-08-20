# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import re
import shlex
from io import StringIO

# See: http://pubs.opengroup.org/onlinepubs/000095399/basedefs/xbd_chap08.html
# or look at the 'param_expand()' function in the subst.c file in the bash
# source tarball...
SHELL_VAR_RULE = r"[a-zA-Z_]+[a-zA-Z0-9_]*"

# Quote format strings
_SQUOT = "'%s'"
_DQUOT = '"%s"'
_TSQUOT = '"""%s"""'
_TDQUOT = "\'\'\'%s\'\'\'"


def _contains_shell_variable(text):
    for r in [
        # Basic variables
        re.compile(r"\$" + SHELL_VAR_RULE),
        # Things like $?, $0, $-, $@
        re.compile(r"\$[0-9#\?\-@\*]"),
        # Things like ${blah:1} - but this one
        # gets very complex so just try the
        # simple path
        re.compile(r"\$\{.+\}"),
    ]:
        if r.search(text):
            return True
    return False


class SysConf(dict):
    """A dict-like object for reading and writing sysconfig files.

    :param contents:
        The sysconfig file to parse: a list of lines, a file-like object,
        or a string (treated as file content).
    """

    def __init__(self, contents):
        super().__init__()
        self._order = []  # ordered list of keys as originally seen
        self._comments = {}  # key -> list of comment/blank lines before it
        self._inline_comments = {}  # key -> inline comment string (after value)
        self._final_comments = []  # trailing comment/blank lines after last key
        self.sections = []  # sysconfig files have no INI sections
        self._parse(contents)

    def _parse(self, contents):
        if isinstance(contents, (list, tuple)):
            lines = list(contents)
        elif isinstance(contents, str):
            lines = contents.splitlines()
        elif hasattr(contents, "read"):
            data = contents.read()
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            lines = data.splitlines()
        else:
            lines = []

        pending = []  # accumulate comment/blank lines until next key
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                pending.append(line)
                continue
            if "=" in line:
                idx = line.index("=")
                key = line[:idx].strip()
                rest = line[idx + 1 :]
                value = self._unquote(rest.strip())
                self._comments[key] = pending
                pending = []
                self._inline_comments[key] = ""
                self._order.append(key)
                super().__setitem__(key, value)
            else:
                pending.append(line)

        self._final_comments = pending

    def _unquote(self, value):
        if len(value) >= 2:
            if (value[0] == '"' and value[-1] == '"') or (
                value[0] == "'" and value[-1] == "'"
            ):
                return value[1:-1]
        return value

    def __setitem__(self, key, value):
        if key not in self:
            self._order.append(key)
            self._comments[key] = []
            self._inline_comments[key] = ""
        super().__setitem__(key, value)

    def __delitem__(self, key):
        super().__delitem__(key)
        if key in self._order:
            self._order.remove(key)
        self._comments.pop(key, None)
        self._inline_comments.pop(key, None)

    def __str__(self):
        lines = []
        written = set()
        for key in self._order:
            if key not in self:
                continue
            for comment_line in self._comments.get(key, []):
                lines.append(comment_line)
            val = self._quote(self[key])
            key_q = self._quote(key)
            inline = self._inline_comments.get(key, "")
            lines.append("%s%s%s%s" % (key_q, "=", val, inline))
            written.add(key)
        # Write any newly-added keys not in original parse order
        for key in self:
            if key not in written:
                val = self._quote(self[key])
                key_q = self._quote(key)
                lines.append("%s%s%s" % (key_q, "=", val))
        for comment_line in self._final_comments:
            lines.append(comment_line)
        return "\n".join(lines)

    def _get_single_quote(self, value):
        if '"' in value:
            return _SQUOT
        return _DQUOT

    def _get_triple_quote(self, value):
        if '"""' not in value:
            return _TDQUOT
        return _TSQUOT

    def _quote(self, value, multiline=False):
        if not isinstance(value, str):
            raise ValueError('Value "%s" is not a string' % (value))
        if not value:
            return ""
        quot_func = None
        if value[0] in ['"', "'"] and value[-1] in ['"', "'"]:
            if len(value) == 1:
                quot_func = (
                    lambda x: self._get_single_quote(x) % x
                )  # noqa: E731
        else:
            # Quote whitespace if it isn't the start + end of a shell command
            if value.strip().startswith("$(") and value.strip().endswith(")"):
                pass
            else:
                if re.search(r"[\t\r\n ]", value):
                    if _contains_shell_variable(value):
                        # If it contains shell variables then we likely want to
                        # leave it alone since the shlex.quote function likes
                        # to use single quotes which won't get expanded...
                        if re.search(r"[\n\"']", value):
                            quot_func = (
                                lambda x: self._get_triple_quote(x) % x
                            )  # noqa: E731
                        else:
                            quot_func = (
                                lambda x: self._get_single_quote(x) % x
                            )  # noqa: E731
                    else:
                        quot_func = shlex.quote
        if not quot_func:
            return value
        return quot_func(value)
