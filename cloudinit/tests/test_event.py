# This file is part of cloud-init. See LICENSE file for license information.
"""Tests related to cloudinit.event module."""

from unittest import TestCase

import pytest

from cloudinit.event import (
    EventType,
    get_enabled_events,
    get_update_events_config
)


class TestEvent:
    def test_events_to_config(self):
        """Validate update_events dictionary maps to expected type map."""
        events = {
            'network': set([EventType.BOOT_NEW_INSTANCE, EventType.BOOT])
        }

        TestCase().assertCountEqual(
            get_update_events_config(events)['network']['when'],
            ['boot', 'boot-new-instance']
        )

    @pytest.mark.parametrize('default_events,config_events,expected_enabled', [
        (['boot-new-instance'], ['boot'], {EventType.BOOT}),
        (['boot-new-instance'], [], set()),
    ])
    def test_get_enabled_events_defaults_filter_datasource(
        self, default_events, config_events, expected_enabled
    ):
        allowed = get_enabled_events(
            {'network': {'when': config_events}},
            {'network': {'when': default_events}}
        )

        assert allowed == {'network': expected_enabled}
