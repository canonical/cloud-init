# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from .config_source import ConfigSource


class ConfigNamespace(ConfigSource):
    """Specifies the Config Namespace."""
    pass

# vi: ts=4 expandtab
