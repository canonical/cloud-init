# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from StringIO import StringIO

import pipes
import re

# This library is used to parse/write
# out the various sysconfig files edited
#
# It has to be slightly modified though
# to ensure that all values are quoted/unquoted correctly
# since these configs are usually sourced into
# bash scripts...
import configobj



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
        if not isinstance(value, (str, basestring)):
            raise ValueError('Value "%s" is not a string' % (value))
        if len(value) == 0:
            return ''
        quot_func = (lambda x: str(x))
        if value[0] in ['"', "'"] and value[-1] in ['"', "'"]:
            if len(value) == 1:
                quot_func = self._get_single_quote
        else:
            # Quote whitespace if it isn't the start + end of a shell command
            white_space_ok = False
            if value.strip().startswith("$(") and value.strip().endswith(")"):
                white_space_ok = True
            if re.search(r"[\t\r\n ]", value) and not white_space_ok:
                quot_func = pipes.quote
        return quot_func(value)

    def _write_line(self, indent_string, entry, this_entry, comment):
        # Ensure it is formatted fine for
        # how these sysconfig scripts are used
        if this_entry.startswith("'") or this_entry.startswith('"'):
            val = this_entry
        val = self._decode_element(self._quote(this_entry))
        key = self._decode_element(self._quote(entry))
        cmnt = self._decode_element(comment)
        return '%s%s%s%s%s' % (indent_string,
                               key,
                               self._a_to_u('='),
                               val,
                               cmnt)

