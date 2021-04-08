# This file is part of cloud-init. See LICENSE file for license information.
"""Classes and functions related to event handling."""

import copy

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


class EventType(object):
    """Event types which can generate maintenance requests for cloud-init."""

    BOOT = "System boot"
    BOOT_NEW_INSTANCE = "New instance first boot"

    # Cloud-init should grow support for the follow event types:
    # HOTPLUG
    # METADATA_CHANGE
    # USER_REQUEST


EventTypeMap = {
    'boot': EventType.BOOT,
    'boot-new-instance': EventType.BOOT_NEW_INSTANCE,
}


# inverted mapping
EventNameMap = {v: k for k, v in EventTypeMap.items()}


def get_enabled_events(config_events: dict, default_events: dict) -> dict:
    """Determine which update events are allowed.

    Merge datasource capabilities with system config to determine events
    """
    # updates:
    #   network:
    #     when: [boot]

    LOG.debug('updates user: %s', config_events)
    LOG.debug('updates default: %s', default_events)

    # If a key exists in multiple places, the first in the list wins.
    updates = util.mergemanydict([
        copy.deepcopy(config_events),
        copy.deepcopy(default_events),
    ])
    LOG.debug('updates merged: %s', updates)

    events = {}
    for etype in [scope for scope, val in default_events.items()
                  if type(val) == dict and 'when' in val]:
        events[etype] = (
            set([EventTypeMap.get(evt)
                 for evt in updates.get(etype, {}).get('when', [])
                 if evt in EventTypeMap]))

    LOG.debug('updates allowed: %s', events)
    return events


def get_update_events_config(update_events: dict) -> dict:
    """Return a dictionary of updates config."""
    evt_cfg = {}
    for scope, events in update_events.items():
        evt_cfg[scope] = {'when': [EventNameMap[evt] for evt in events]}
    return evt_cfg

# vi: ts=4 expandtab
