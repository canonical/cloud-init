# This file is part of cloud-init. See LICENSE file for license information.
"""Classes and functions related to event handling."""

from enum import Enum
from typing import Dict, Set

from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class EventScope(Enum):
    # NETWORK is currently the only scope, but we want to leave room to
    # grow other scopes (e.g., STORAGE) without having to make breaking
    # changes to the user config
    NETWORK = "network"

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.value


class EventType(Enum):
    """Event types which can generate maintenance requests for cloud-init."""

    # Cloud-init should grow support for the follow event types:
    # HOTPLUG
    # METADATA_CHANGE
    # USER_REQUEST

    BOOT = "boot"
    BOOT_NEW_INSTANCE = "boot-new-instance"
    BOOT_LEGACY = "boot-legacy"
    HOTPLUG = "hotplug"

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.value


def userdata_to_events(user_config: dict) -> Dict[EventScope, Set[EventType]]:
    """Convert userdata into update config format defined on datasource.

    Userdata is in the form of (e.g):
    {'network': {'when': ['boot']}}

    DataSource config is in the form of:
    {EventScope.Network: {EventType.BOOT}}

    Take the first and return the second
    """
    update_config = {}
    for scope, scope_list in user_config.items():
        try:
            new_scope = EventScope(scope)
        except ValueError as e:
            LOG.warning(
                "%s! Update data will be ignored for '%s' scope",
                str(e),
                scope,
            )
            continue
        try:
            new_values = [EventType(x) for x in scope_list["when"]]
        except ValueError as e:
            LOG.warning(
                "%s! Update data will be ignored for '%s' scope",
                str(e),
                scope,
            )
            new_values = []
        update_config[new_scope] = set(new_values)

    return update_config


# vi: ts=4 expandtab
