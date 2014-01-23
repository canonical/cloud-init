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

from cloudinit import log as logging

LOG = logging.getLogger(__name__)


def import_module(module_name):
    __import__(module_name)
    return sys.modules[module_name]


def find_module(base_name, search_paths, required_attrs=None):
    found_places = []
    if not required_attrs:
        required_attrs = []
    # NOTE(harlowja): translate the search paths to include the base name.
    real_paths = []
    for path in search_paths:
        real_path = []
        if path:
            real_path.extend(path.split("."))
        real_path.append(base_name)
        full_path = '.'.join(real_path)
        real_paths.append(full_path)
    LOG.debug("Looking for modules %s that have attributes %s",
              real_paths, required_attrs)
    for full_path in real_paths:
        mod = None
        try:
            mod = import_module(full_path)
        except ImportError as e:
            LOG.debug("Failed at attempted import of '%s' due to: %s",
                      full_path, e)
        if not mod:
            continue
        found_attrs = 0
        for attr in required_attrs:
            if hasattr(mod, attr):
                found_attrs += 1
        if found_attrs == len(required_attrs):
            found_places.append(full_path)
    LOG.debug("Found %s with attributes %s in %s", base_name,
              required_attrs, found_places)
    return found_places
