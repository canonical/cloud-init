# Copyright (C) 2016 Canonical Ltd.
# Copyright (C) 2016 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class GuestCustEventEnum(object):
    """Specifies different types of Guest Customization Events"""

    GUESTCUST_EVENT_CUSTOMIZE_FAILED = 100
    GUESTCUST_EVENT_NETWORK_SETUP_FAILED = 101
    GUESTCUST_EVENT_ENABLE_NICS = 103
    GUESTCUST_EVENT_QUERY_NICS = 104

# vi: ts=4 expandtab
