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

from cloudinit.distros.parsers import chop_comment


# See: man hosts
# or http://unixhelp.ed.ac.uk/CGI/man-cgi?hosts
# or http://tinyurl.com/6lmox3
class HostsConf(object):
    def __init__(self, text):
        self._text = text
        self._contents = None

    def parse(self):
        if self._contents is None:
            self._contents = self._parse(self._text)

    def get_entry(self, ip):
        self.parse()
        options = []
        for (line_type, components) in self._contents:
            if line_type == 'option':
                (pieces, _tail) = components
                if len(pieces) and pieces[0] == ip:
                    options.append(pieces[1:])
        return options

    def del_entries(self, ip):
        self.parse()
        n_entries = []
        for (line_type, components) in self._contents:
            if line_type != 'option':
                n_entries.append((line_type, components))
                continue
            else:
                (pieces, _tail) = components
                if len(pieces) and pieces[0] == ip:
                    pass
                elif len(pieces):
                    n_entries.append((line_type, list(components)))
        self._contents = n_entries

    def add_entry(self, ip, canonical_hostname, *aliases):
        self.parse()
        self._contents.append(('option',
                              ([ip, canonical_hostname] + list(aliases), '')))

    def _parse(self, contents):
        entries = []
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(('blank', [line]))
                continue
            (head, tail) = chop_comment(line.strip(), '#')
            if not len(head):
                entries.append(('all_comment', [line]))
                continue
            entries.append(('option', [head.split(None), tail]))
        return entries

    def __str__(self):
        self.parse()
        contents = StringIO()
        for (line_type, components) in self._contents:
            if line_type == 'blank':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'all_comment':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'option':
                (pieces, tail) = components
                pieces = [str(p) for p in pieces]
                pieces = "\t".join(pieces)
                contents.write("%s%s\n" % (pieces, tail))
        return contents.getvalue()
