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

# This library is used to parse/write
# out the various sysconfig files edited
#
# It has to be slightly modified though
# to ensure that all values are quoted
# since these configs are usually sourced into
# bash scripts...
from configobj import ConfigObj

# See: http://tiny.cc/oezbgw
D_QUOTE_CHARS = {
    "\"": "\\\"",
    "(": "\\(",
    ")": "\\)",
    "$": '\$',
    '`': '\`',
}

# This class helps adjust the configobj
# writing to ensure that when writing a k/v
# on a line, that they are properly quoted
# and have no spaces between the '=' sign.
# - This is mainly due to the fact that
# the sysconfig scripts are often sourced
# directly into bash/shell scripts so ensure
# that it works for those types of use cases.
class QuotingConfigObj(ConfigObj):
    def __init__(self, lines):
        ConfigObj.__init__(self, lines,
                           interpolation=False,
                           write_empty_values=True)

    def _quote_posix(self, text):
        if not text:
            return ''
        for (k, v) in D_QUOTE_CHARS.iteritems():
            text = text.replace(k, v)
        return '"%s"' % (text)

    def _quote_special(self, text):
        if text.lower() in ['yes', 'no', 'true', 'false']:
            return text
        else:
            return self._quote_posix(text)

    def _write_line(self, indent_string, entry, this_entry, comment):
        # Ensure it is formatted fine for
        # how these sysconfig scripts are used
        val = self._decode_element(self._quote(this_entry))
        # Single quoted strings should
        # always work.
        if not val.startswith("'"):
            # Perform any special quoting
            val = self._quote_special(val)
        key = self._decode_element(self._quote(entry, multiline=False))
        cmnt = self._decode_element(comment)
        return '%s%s%s%s%s' % (indent_string,
                               key,
                               "=",
                               val,
                               cmnt)

