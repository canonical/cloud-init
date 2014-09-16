# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import sys


def import_module(module_name):
    __import__(module_name)
    return sys.modules[module_name]


def find_module(base_name, search_paths, required_attrs=None):
    if not required_attrs:
        required_attrs = []
    # NOTE(harlowja): translate the search paths to include the base name.
    lookup_paths = []
    for path in search_paths:
        real_path = []
        if path:
            real_path.extend(path.split("."))
        real_path.append(base_name)
        full_path = '.'.join(real_path)
        lookup_paths.append(full_path)
    found_paths = []
    for full_path in lookup_paths:
        mod = None
        try:
            mod = import_module(full_path)
        except ImportError:
            pass
        if not mod:
            continue
        found_attrs = 0
        for attr in required_attrs:
            if hasattr(mod, attr):
                found_attrs += 1
        if found_attrs == len(required_attrs):
            found_paths.append(full_path)
    return (found_paths, lookup_paths)
