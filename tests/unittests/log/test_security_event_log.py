# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log.security_event_log"""

import json

import pytest

from cloudinit.log import loggers, security_event_log
from cloudinit.log.security_event_log import (
    OWASPEventLevel,
    OWASPEventType,
    sec_log_password_changed,
    sec_log_system_shutdown,
    sec_log_user_created,
)
from cloudinit.util import get_hostname


class TestBuildEventString:
    """Tests for _build_event_string function."""

    @pytest.mark.parametrize(
        "event_type,params,expected",
        [
            (OWASPEventType.SYS_SHUTDOWN, None, "sys_shutdown"),
            (
                OWASPEventType.AUTHN_PASSWORD_CHANGE,
                ["testuser"],
                "authn_password_change:testuser",
            ),
            (
                OWASPEventType.USER_CREATED,
                ["cloud-init", "newuser", "groups=wheel"],
                "user_created:cloud-init,newuser,groups=wheel",
            ),
            (
                OWASPEventType.USER_CREATED,
                ["cloud-init", None, "newuser"],
                "user_created:cloud-init,newuser",
            ),
        ],
        ids=[
            "no_params",
            "single_param",
            "multiple_params",
            "filters_none_params",
        ],
    )
    def test_event_string_formatting(self, event_type, params, expected):
        """Test event string formatting with various parameter combinations."""
        result = security_event_log._build_event_string(event_type, params)
        assert result == expected


class TestBuildSecurityEvent:
    """Tests for _build_security_event function."""

    def test_event_contains_required_owasp_fields(self):
        """Test that built event contains all required OWASP fields."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            event_params=["cloud-init", "testuser"],
        )

        assert "datetime" in event
        assert event["appid"] == "canonical.cloud_init"
        assert event["event"] == "user_created:cloud-init,testuser"
        assert event["level"] == "INFO"
        assert event["description"] == "Test event"
        assert "hostname" in event

    def test_event_with_additional_data(self):
        """Test event includes additional data when provided."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"groups": "wheel", "shell": "/bin/bash"},
        )

        assert event["groups"] == "wheel"
        assert event["shell"] == "/bin/bash"

    def test_additional_data_does_not_overwrite_core_fields(self):
        """Test that additional data cannot overwrite core fields."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"appid": "malicious.app", "level": "CRITICAL"},
        )

        assert event["appid"] == "canonical.cloud_init"
        assert event["level"] == "INFO"

    def test_timestamp_is_iso_format(self):
        """Test that datetime is in ISO 8601 format."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
        )

        # ISO 8601 format check - should contain 'T' separator
        assert "T" in event["datetime"]
        # Should end with timezone info (e.g., +00:00)
        assert "+" in event["datetime"] or "Z" in event["datetime"]


class TestLogSecurityEvent:
    """Tests for _log_security_event function."""

    def test_writes_json_to_file(self, caplog):
        """Test that event is written to log file as JSON."""
        with caplog.at_level(loggers.SECURITY):
            security_event_log._log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.INFO,
                description="User created successfully",
                event_params=["cloud-init", "testuser"],
            )
        event = json.loads(caplog.records[0].msg)

        assert event["event"] == "user_created:cloud-init,testuser"
        assert event["level"] == "INFO"
        assert event["appid"] == "canonical.cloud_init"

    def test_appends_multiple_events(self, caplog):
        """Test that multiple events are appended to the log file."""
        with caplog.at_level(loggers.SECURITY):
            security_event_log._log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.INFO,
                description="First user",
                event_params=["cloud-init", "user1"],
            )

            security_event_log._log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.INFO,
                description="Second user",
                event_params=["cloud-init", "user2"],
            )

        assert len(caplog.records) == 2
        event1 = json.loads(caplog.records[0].msg)
        event2 = json.loads(caplog.records[1].msg)
        assert "user1" in event1["event"]
        assert "user2" in event2["event"]


class TestUserCreatedEvent:
    """Tests for sec_log_user_created function."""

    @pytest.mark.parametrize("user_created", (True, False))
    def test_logs_user_created_event(self, user_created, caplog):
        """Test logging a user creation event."""

        @sec_log_user_created
        def user_created_test(name, **kwargs):
            # Distro.create_user returns False when no new user is created.
            return user_created

        with caplog.at_level(loggers.SECURITY):
            user_created_test(
                name="testuser",
            )

        if not user_created:
            assert 0 == len(caplog.records)
            return

        # Create user security event happens only when user is created
        event = json.loads(caplog.records[0].msg)

        assert event.pop("datetime")
        assert {
            "appid": "canonical.cloud_init",
            "event": "user_created:cloud-init,testuser",
            "description": "User 'testuser' was created",
            "hostname": get_hostname(),
            "level": "WARN",
        } == event


class TestPasswordChangedEvent:
    """Tests for sec_log_password_changed function."""

    def test_logs_password_changed_event(self, caplog):
        """Test logging a password change event."""

        @sec_log_password_changed
        def set_passwd_test(user):
            pass

        with caplog.at_level(loggers.SECURITY):
            set_passwd_test(user="testuser")
            set_passwd_test("testuser")  # Test with positional params

        expected_value = {
            "appid": "canonical.cloud_init",
            "event": "authn_password_change:cloud-init,testuser",
            "description": "Password changed for user 'testuser'",
            "hostname": get_hostname(),
            "level": "INFO",
        }

        for record in caplog.records:
            event = json.loads(record.msg)
            assert event.pop("datetime")
            assert expected_value == event


class TestSystemShutdownEvent:
    """Tests for sec_log_system_shutdown function."""

    @pytest.mark.parametrize(
        "mode,delay,expected_event,expected_descr",
        (
            (
                "poweroff",
                "+5",
                "sys_shutdown:cloud-init",
                "System shutdown initiated (mode=poweroff)",
            ),
            (
                "reboot",
                "now",
                "sys_restart:cloud-init",
                "System restart initiated",
            ),
        ),
    )
    def test_logs_system_shutdown_event(
        self, mode, delay, expected_event, expected_descr, caplog
    ):
        """Test logging a system shutdown event."""

        @sec_log_system_shutdown
        def shutdown_test(mode, delay):
            pass

        with caplog.at_level(loggers.SECURITY):
            shutdown_test(
                mode=mode,
                delay=delay,
            )

        event = json.loads(caplog.records[0].msg)
        assert event.pop("datetime")
        expected = {
            "appid": "canonical.cloud_init",
            "delay": delay,
            "description": expected_descr,
            "event": expected_event,
            "hostname": get_hostname(),
            "level": "INFO",
        }
        if mode != "reboot":
            expected["mode"] = mode
        assert expected == event


class TestEventTypeEnums:
    """Tests for event type enum values."""

    @pytest.mark.parametrize(
        "event_type,expected_value",
        [
            (OWASPEventType.AUTHN_PASSWORD_CHANGE, "authn_password_change"),
            (OWASPEventType.SYS_SHUTDOWN, "sys_shutdown"),
            (OWASPEventType.SYS_RESTART, "sys_restart"),
            (OWASPEventType.USER_CREATED, "user_created"),
        ],
        ids=[
            "authn_password_change",
            "sys_shutdown",
            "sys_restart",
            "user_created",
        ],
    )
    def test_event_type_values(self, event_type, expected_value):
        """Test event type enum values."""
        assert event_type.value == expected_value
