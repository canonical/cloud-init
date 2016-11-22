# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import six
from six import StringIO

import pipes
import re

# This library is used to parse/write
# out the various sysconfig files edited (best attempt effort)
#
# It has to be slightly modified though
# to ensure that all values are quoted/unquoted correctly
# since these configs are usually sourced into
# bash scripts...
import configobj

# See: http://pubs.opengroup.org/onlinepubs/000095399/basedefs/xbd_chap08.html
# or look at the 'param_expand()' function in the subst.c file in the bash
# source tarball...
SHELL_VAR_RULE = r'[a-zA-Z_]+[a-zA-Z0-9_]*'
SHELL_VAR_REGEXES = [
    # Basic variables
    re.compile(r"\$" + SHELL_VAR_RULE),
    # Things like $?, $0, $-, $@
    re.compile(r"\$[0-9#\?\-@\*]"),
    # Things like ${blah:1} - but this one
    # gets very complex so just try the
    # simple path
    re.compile(r"\$\{.+\}"),
]


def _contains_shell_variable(text):
    for r in SHELL_VAR_REGEXES:
        if r.search(text):
            return True
    return False


class SysConf(configobj.ConfigObj):
    def __init__(self, contents):
        configobj.ConfigObj.__init__(self, contents,
                                     interpolation=False,
                                     write_empty_values=True)

    def __str__(self):
        contents = self.write()
        out_contents = StringIO()
        if isinstance(contents, (list, tuple)):
            out_contents.write("\n".join(contents))
        else:
            out_contents.write(str(contents))
        return out_contents.getvalue()

    def _quote(self, value, multiline=False):
        if not isinstance(value, six.string_types):
            raise ValueError('Value "%s" is not a string' % (value))
        if len(value) == 0:
            return ''
        quot_func = None
        if value[0] in ['"', "'"] and value[-1] in ['"', "'"]:
            if len(value) == 1:
                quot_func = (lambda x: self._get_single_quote(x) % x)
        else:
            # Quote whitespace if it isn't the start + end of a shell command
            if value.strip().startswith("$(") and value.strip().endswith(")"):
                pass
            else:
                if re.search(r"[\t\r\n ]", value):
                    if _contains_shell_variable(value):
                        # If it contains shell variables then we likely want to
                        # leave it alone since the pipes.quote function likes
                        # to use single quotes which won't get expanded...
                        if re.search(r"[\n\"']", value):
                            quot_func = (lambda x:
                                         self._get_triple_quote(x) % x)
                        else:
                            quot_func = (lambda x:
                                         self._get_single_quote(x) % x)
                    else:
                        quot_func = pipes.quote
        if not quot_func:
            return value
        return quot_func(value)

    def _write_line(self, indent_string, entry, this_entry, comment):
        # Ensure it is formatted fine for
        # how these sysconfig scripts are used
        val = self._decode_element(self._quote(this_entry))
        key = self._decode_element(self._quote(entry))
        cmnt = self._decode_element(comment)
        return '%s%s%s%s%s' % (indent_string,
                               key,
                               self._a_to_u('='),
                               val,
                               cmnt)

# vi: ts=4 expandtab
