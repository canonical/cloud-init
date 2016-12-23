# Copyright (C) 2015 Canonical Ltd.
# Copyright (C) 2015 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class BootProtoEnum(object):
    """Specifies the NIC Boot Settings."""

    DHCP = 'dhcp'
    STATIC = 'static'

# vi: ts=4 expandtab
