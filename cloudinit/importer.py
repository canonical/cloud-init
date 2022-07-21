# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import importlib
from types import ModuleType
from typing import Optional, Sequence


def import_module(module_name: str) -> ModuleType:
    return importlib.import_module(module_name)


def _count_attrs(
    module_name: str, attrs: Optional[Sequence[str]] = None
) -> int:
    found_attrs = 0
    if not attrs:
        return found_attrs
    mod = importlib.import_module(module_name)
    for attr in attrs:
        if hasattr(mod, attr):
            found_attrs += 1
    return found_attrs


def find_module(
    base_name: str,
    search_paths: Sequence[str],
    required_attrs: Optional[Sequence[str]] = None,
) -> tuple:
    """Finds specified modules"""
    if not required_attrs:
        required_attrs = []
    # NOTE(harlowja): translate the search paths to include the base name.
    lookup_paths = []
    for path in search_paths:
        real_path = []
        if path:
            real_path.extend(path.split("."))
        real_path.append(base_name)
        full_path = ".".join(real_path)
        lookup_paths.append(full_path)
    found_paths = []
    for full_path in lookup_paths:
        if not importlib.util.find_spec(full_path):
            continue
        # Check that required_attrs are all present within the module.
        if _count_attrs(full_path, required_attrs) == len(required_attrs):
            found_paths.append(full_path)
    return (found_paths, lookup_paths)


# vi: ts=4 expandtab
