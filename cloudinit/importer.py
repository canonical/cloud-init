# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

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

# vi: ts=4 expandtab
