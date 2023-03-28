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

import cloudinit.util as util


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


def match_case_insensitive_module_name(ds_name: str) -> Optional[str]:
    """Check the importable datasource modules for a case-insensitive match.
    This string comes from ds-identify.
    """
    if not ds_name.startswith("DataSource"):
        ds_name = f"DataSource{ds_name}"
    modules = {}
    for dir in importlib.util.find_spec(
        "cloudinit.sources"
    ).submodule_search_locations:
        modules.update(util.get_modules_from_dir(dir))
    for module in modules.values():
        if module.lower() == ds_name.lower():
            return module
    return ds_name


def find_module(
    base_name: str,
    search_paths: Sequence[str],
    required_attrs: Optional[Sequence[str]] = None,
) -> tuple:
    """Finds specified modules"""
    if not required_attrs:
        required_attrs = []
    lookup_paths = []
    found_paths = []

    for path in search_paths:
        # Add base name to search paths. Filter out empty paths.
        full_path = ".".join(filter(None, [path, base_name]))
        lookup_paths.append(full_path)
        if not importlib.util.find_spec(full_path):
            continue
        # Check that required_attrs are all present within the module.
        if _count_attrs(full_path, required_attrs) == len(required_attrs):
            found_paths.append(full_path)
    return (found_paths, lookup_paths)
