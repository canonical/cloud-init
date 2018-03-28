# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

__VERSION__ = "18.2"

FEATURES = [
    # supports network config version 1
    'NETWORK_CONFIG_V1',
    # supports network config version 2 (netplan)
    'NETWORK_CONFIG_V2',
]


def version_string():
    return __VERSION__

# vi: ts=4 expandtab
