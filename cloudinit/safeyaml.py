# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import yaml


class _CustomSafeLoader(yaml.SafeLoader):
    def construct_python_unicode(self, node):
        return self.construct_scalar(node)

_CustomSafeLoader.add_constructor(
    u'tag:yaml.org,2002:python/unicode',
    _CustomSafeLoader.construct_python_unicode)


def load(blob):
    return(yaml.load(blob, Loader=_CustomSafeLoader))
