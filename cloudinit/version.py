# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

__VERSION__ = "24.1.7"
_PACKAGED_VERSION = "@@PACKAGED_VERSION@@"

FEATURES = [
    # supports network config version 1
    "NETWORK_CONFIG_V1",
    # supports network config version 2 (netplan)
    "NETWORK_CONFIG_V2",
]


def version_string():
    """Extract a version string from cloud-init."""
    if not _PACKAGED_VERSION.startswith("@@"):
        return _PACKAGED_VERSION
    return __VERSION__
