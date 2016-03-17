# vi: ts=4 expandtab
#
#    Copyright (C) 2016 Canonical Ltd.
#    Copyright (C) 2016 VMware Inc.
#
#    Author: Sankar Tanguturi <stanguturi@vmware.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.


class GuestCustEventEnum:
    """Specifies different types of Guest Customization Events"""

    GUESTCUST_EVENT_CUSTOMIZE_FAILED = 100
    GUESTCUST_EVENT_NETWORK_SETUP_FAILED = 101
    GUESTCUST_EVENT_ENABLE_NICS = 103
    GUESTCUST_EVENT_QUERY_NICS = 104
