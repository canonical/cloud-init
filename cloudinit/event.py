# This file is part of cloud-init. See LICENSE file for license information.

"""Classes and functions related to event handling."""


# Event types which can generate maintenance requests for cloud-init.
class EventType(object):
    BOOT = "System boot"
    BOOT_NEW_INSTANCE = "New instance first boot"
    UDEV = "Udev add|change event on net|storage"

    # TODO: Cloud-init will grow support for the follow event types:
    # METADATA_CHANGE
    # USER_REQUEST


# vi: ts=4 expandtab
