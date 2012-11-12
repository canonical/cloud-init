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


# Parser that knows how to work with /etc/hostname format
class HostnameConf(object):
    def __init__(self, text):
        self._text = text
        self._contents = None

    def parse(self):
        if self._contents is None:
            self._contents = self._parse(self._text)

    def __str__(self):
        self.parse()
        contents = StringIO()
        for (line_type, components) in self._contents:
            if line_type == 'blank':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'all_comment':
                contents.write("%s\n" % (components[0]))
            elif line_type == 'hostname':
                (hostname, tail) = components
                contents.write("%s%s\n" % (hostname, tail))
        # Ensure trailing newline
        contents = contents.getvalue()
        if not contents.endswith("\n"):
            contents += "\n"
        return contents

    @property
    def hostname(self):
        self.parse()
        for (line_type, components) in self._contents:
            if line_type == 'hostname':
                return components[0]
        return None

    def set_hostname(self, your_hostname):
        your_hostname = your_hostname.strip()
        if not your_hostname:
            return
        self.parse()
        replaced = False
        for (line_type, components) in self._contents:
            if line_type == 'hostname':
                components[0] = str(your_hostname)
                replaced = True
        if not replaced:
            self._contents.append(('hostname', [str(your_hostname), '']))

    def _parse(self, contents):
        entries = []
        hostnames_found = set()
        for line in contents.splitlines():
            if not len(line.strip()):
                entries.append(('blank', [line]))
                continue
            (head, tail) = chop_comment(line.strip(), '#')
            if not len(head):
                entries.append(('all_comment', [line]))
                continue
            entries.append(('hostname', [head, tail]))
            hostnames_found.add(head)
        if len(hostnames_found) > 1:
            raise IOError("Multiple hostnames (%s) found!"
                           % (hostnames_found))
        return entries
