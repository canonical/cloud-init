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

from cloudinit import util


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


def match_case_insensitive_module_name(mod_name: str) -> Optional[str]:
    """Check the importable datasource modules for a case-insensitive match."""

    # nocloud-net is the only datasource that requires matching on a name that
    # does not match its python module - canonicalize it here
    if "nocloud-net" == mod_name.lower():
        mod_name = mod_name[:-4]
    if not mod_name.startswith("DataSource"):
        mod_name = f"DataSource{mod_name}"
    modules = {}
    # mypy is right to warn here. This isn't a documented method.
    # However it has worked for years without issue, so fixing it is not
    # a high priority. We'll fix it when it breaks.
    spec = importlib.util.find_spec("cloudinit.sources")  # type: ignore
    if spec and spec.submodule_search_locations:
        for dir in spec.submodule_search_locations:
            modules.update(util.get_modules_from_dir(dir))
        for module in modules.values():
            if module.lower() == mod_name.lower():
                return module
    return mod_name


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
        # mypy is right to warn here. This isn't a documented method.
        # However it has worked for years without issue, so fixing it is not
        # a high priority. We'll fix it when it breaks.
        if not importlib.util.find_spec(full_path):  # type: ignore
            continue
        # Check that required_attrs are all present within the module.
        if _count_attrs(full_path, required_attrs) == len(required_attrs):
            found_paths.append(full_path)
    return (found_paths, lookup_paths)
