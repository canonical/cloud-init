# This file is part of cloud-init. See LICENSE file for license information.

"""Tests related to cloudinit.event module."""

import copy
import random
import string

from cloudinit.event import (EventType,
                             EventNameMap,
                             get_allowed_events,
                             get_update_events_config)

from cloudinit.tests.helpers import CiTestCase


def rand_event_names():
    return [random.choice(list(EventNameMap.keys()))
            for x in range(len(EventNameMap.keys()))]


def rand_string(size=6, chars=string.ascii_lowercase):
    return ''.join(random.choice(chars) for x in range(size))


class TestEvent(CiTestCase):
    with_logs = True

    DEFAULT_UPDATE_EVENTS = {'network': set([EventType.BOOT_NEW_INSTANCE]),
                             'storage': set([])}
    DEFAULT_UPDATES_CONFIG = {'policy-version': 1,
                              'network': {'when': ['boot-new-instance']},
                              'storage': {'when': []}}

    def test_events_to_config(self):
        """validate default update_events dictionary maps to default policy"""
        events = copy.deepcopy(self.DEFAULT_UPDATE_EVENTS)
        config = get_update_events_config(events)

        for scope, events in events.items():
            self.assertIn(scope, config)
            for evt in events:
                self.assertIn(evt, EventNameMap)
                self.assertIn(EventNameMap.get(evt),
                              config.get(scope).get('when'))

        self.assertEqual(sorted(config),
                         sorted(self.DEFAULT_UPDATES_CONFIG))

    def test_get_allowed_events_defaults_filter_datasource(self):
        ds_config = {
            'policy-version': 1,
            'network': {'when': rand_event_names()},
            'storage': {'when': rand_event_names()},
        }
        user_data = {}
        allowed = get_allowed_events(
            self.DEFAULT_UPDATES_CONFIG, ds_config, user_data)

        # system config filters out ds capabilities
        self.assertEqual(sorted(allowed), sorted(self.DEFAULT_UPDATE_EVENTS))

    def test_get_allowed_events_uses_system_config_scopes(self):
        ds_config = {
            'policy-version': 1,
            'network': {'when': rand_event_names()},
            'storage': {'when': rand_event_names()},
        }
        user_data = {}
        rand_scope = rand_string()
        rand_events = rand_event_names()
        sys_config = {'policy-version': 1, rand_scope: {'when': rand_events}}

        self.assertNotIn(rand_scope, ds_config)
        allowed = get_allowed_events(sys_config, ds_config, user_data)
        self.assertIn(rand_scope, allowed)

    def test_get_allowed_events_user_data_overrides_sys(self):
        ds_config = {
            'policy-version': 1,
            'network': {'when': ['boot', 'boot-new-instance', 'hotplug']},
        }
        user_config = {
            'policy-version': 1,
            'network': {'when': ['boot', 'boot-new-instance', 'hotplug']},
        }
        sys_config = {
            'policy-version': 1,
            'network': {'when': ['boot-new-instance']},
        }
        allowed = get_allowed_events(sys_config, ds_config, user_config)
        self.assertIn(EventType.HOTPLUG, allowed['network'])


# vi: ts=4 expandtab
