# Copyright (C) 2016 Canonical Ltd.
# Copyright (C) 2016 VMware Inc.
#
# Author: Sankar Tanguturi <stanguturi@vmware.com>
#
# This file is part of cloud-init. See LICENSE file for license information.


class GuestCustErrorEnum:
    """Specifies different errors of Guest Customization engine"""

    GUESTCUST_ERROR_SUCCESS = 0
    GUESTCUST_ERROR_SCRIPT_DISABLED = 6
    GUESTCUST_ERROR_WRONG_META_FORMAT = 9


# vi: ts=4 expandtab
