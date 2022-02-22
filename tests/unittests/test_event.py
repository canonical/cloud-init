# This file is part of cloud-init. See LICENSE file for license information.
"""Tests related to cloudinit.event module."""
from cloudinit.event import EventScope, EventType, userdata_to_events


class TestEvent:
    def test_userdata_to_events(self):
        userdata = {"network": {"when": ["boot"]}}
        expected = {EventScope.NETWORK: {EventType.BOOT}}
        assert expected == userdata_to_events(userdata)

    def test_invalid_scope(self, caplog):
        userdata = {"networkasdfasdf": {"when": ["boot"]}}
        userdata_to_events(userdata)
        assert (
            "'networkasdfasdf' is not a valid EventScope! Update data "
            "will be ignored for 'networkasdfasdf' scope" in caplog.text
        )

    def test_invalid_event(self, caplog):
        userdata = {"network": {"when": ["bootasdfasdf"]}}
        userdata_to_events(userdata)
        assert (
            "'bootasdfasdf' is not a valid EventType! Update data "
            "will be ignored for 'network' scope" in caplog.text
        )
