# This file is part of cloud-init. See LICENSE file for license information.
"""Classes and functions related to event handling."""

import copy

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


# Event types which can generate maintenance requests for cloud-init.
class EventType(object):
    BOOT = "System boot"
    BOOT_NEW_INSTANCE = "New instance first boot"

    # TODO: Cloud-init will grow support for the follow event types:
    # UDEV
    # METADATA_CHANGE
    # USER_REQUEST


EventTypeMap = {
    'boot': EventType.BOOT,
    'boot-new-instance': EventType.BOOT_NEW_INSTANCE,
}


# inverted mapping
EventNameMap = {v: k for k, v in EventTypeMap.items()}


def get_allowed_events(sys_events, ds_events, user_events):
    '''Merge datasource capabilities with system config to determine which
       update events are allowed.'''

    # updates:
    #   policy-version: 1
    #   network:
    #     when: [boot-new-instance, boot, hotplug]
    #   storage:
    #     when: [boot-new-instance, hotplug]
    #     watch: http://169.254.169.254/metadata/storage_config/

    LOG.debug('updates: user     cfg: %s', user_events)
    LOG.debug('updates: system   cfg: %s', sys_events)
    LOG.debug('updates: datasrc caps: %s', ds_events)

    updates = util.mergemanydict([copy.deepcopy(user_events),
                                  copy.deepcopy(sys_events),
                                  copy.deepcopy(ds_events)])
    LOG.debug('updates: merged  cfg: %s', updates)

    events = {}
    for etype in [scope for scope, val in sys_events.items()
                  if type(val) == dict and 'when' in val]:
        events[etype] = (
            set([EventTypeMap.get(evt)
                 for evt in updates.get(etype, {}).get('when', [])
                 if evt in EventTypeMap]))

    LOG.debug('updates: allowed events: %s', events)
    return events


def get_update_events_config(update_events):
    '''Return a dictionary of updates config'''
    evt_cfg = {'policy-version': 1}
    for scope, events in update_events.items():
        evt_cfg[scope] = {'when': [EventNameMap[evt] for evt in events]}

    return evt_cfg


# vi: ts=4 expandtab
