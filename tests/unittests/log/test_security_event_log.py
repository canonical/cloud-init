# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log.security_event_log"""

import json

import pytest

from cloudinit.log import loggers, security_event_log
from cloudinit.log.security_event_log import (
    OWASPEventLevel,
    OWASPEventType,
    sec_log_password_changed,
    sec_log_password_changed_batch,
    sec_log_system_shutdown,
    sec_log_user_created,
)
from cloudinit.util import get_hostname

MPATH = "cloudinit.log.security_event_log."


class TestBuildEventString:
    """Tests for _build_event_string function."""

    @pytest.mark.parametrize(
        "event_type,params,expected",
        [
            pytest.param(
                OWASPEventType.SYS_SHUTDOWN,
                None,
                "sys_shutdown",
                id="no_params",
            ),
            pytest.param(
                OWASPEventType.AUTHN_PASSWORD_CHANGE,
                ["testuser"],
                "authn_password_change:testuser",
                id="single_param",
            ),
            pytest.param(
                OWASPEventType.USER_CREATED,
                ["cloud-init", "newuser", "groups:wheel"],
                "user_created:cloud-init,newuser,groups:wheel",
                id="multiple_params",
            ),
            pytest.param(
                OWASPEventType.USER_CREATED,
                ["cloud-init", None, "newuser"],
                "user_created:cloud-init,newuser",
                id="filters_none_params",
            ),
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
        assert event["appid"] == "canonical.cloud-init"
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

        assert event["appid"] == "canonical.cloud-init"
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
        assert event["appid"] == "canonical.cloud-init"

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

    @pytest.mark.parametrize(
        "uc_kwargs,event_id,description",
        [
            pytest.param(
                {},
                "user_created:cloud-init,testuser",
                "User 'testuser' was created",
                id="user_created_logs_event",
            ),
            pytest.param(
                {"groups": ["grp1", "grp2"]},
                "user_created:cloud-init,testuser,groups:grp1,grp2",
                "User 'testuser' was created in groups: grp1,grp2",
                id="user_created_with_groups_logs_event",
            ),
            pytest.param(
                {"sudo": True, "groups": ["grp1"]},
                "user_created:cloud-init,testuser,groups:grp1,sudo",
                "User 'testuser' was created in groups: grp1,sudo",
                id="user_created_with_sudo_and_groups_logs_event",
            ),
            pytest.param(
                {"doas": True, "groups": ["grp2"]},
                "user_created:cloud-init,testuser,groups:grp2,doas",
                "User 'testuser' was created in groups: grp2,doas",
                id="user_created_with_doas_and_groups_logs_event",
            ),
        ],
    )
    def test_logs_user_created_event(
        self, uc_kwargs, event_id, description, caplog
    ):
        """Test logging a user creation event."""

        class DecoratedSetPasswordTest:
            @sec_log_user_created
            def user_created_decorator_test(self, name, **kwargs):
                return

        with caplog.at_level(loggers.SECURITY):
            DecoratedSetPasswordTest().user_created_decorator_test(
                name="testuser",
                **uc_kwargs,
            )

        event = json.loads(caplog.records[0].msg)

        assert event.pop("datetime")
        assert {
            "appid": "canonical.cloud-init",
            "event": event_id,
            "description": description,
            "hostname": get_hostname(),
            "level": "WARN",
            "type": "security",
        } == event


class TestPasswordChangedEvent:
    """Tests for sec_log_password_changed function."""

    def test_logs_password_changed_event(self, caplog):
        """Test logging a password change event."""

        class DecoratedSetPasswordTest:
            @sec_log_password_changed
            def set_passwd(self, user):
                pass

        method_test = DecoratedSetPasswordTest()

        with caplog.at_level(loggers.SECURITY):
            method_test.set_passwd(user="testuser")
            method_test.set_passwd("testuser")  # Test positional params

        expected_value = {
            "appid": "canonical.cloud-init",
            "event": "authn_password_change:cloud-init,testuser",
            "description": "Password changed for user 'testuser'",
            "hostname": get_hostname(),
            "level": "INFO",
            "type": "security",
        }

        for record in caplog.records:
            event = json.loads(record.msg)
            assert event.pop("datetime")
            assert expected_value == event


class TestPasswordChangedBatchEvent:
    """Tests for sec_log_password_changed_batch function."""

    def test_logs_password_changed_event_for_each_user(self, caplog):
        """Test logging a password change event."""

        class DecoratedChpasswdTest:
            @sec_log_password_changed_batch
            def chpasswd(self, plist_in):
                pass

        method_test = DecoratedChpasswdTest()

        with caplog.at_level(loggers.SECURITY):
            method_test.chpasswd(plist_in=(("testuser", "pw1"),))

        expected_value = {
            "appid": "canonical.cloud-init",
            "event": "authn_password_change:cloud-init,testuser",
            "description": "Password changed for user 'testuser'",
            "hostname": get_hostname(),
            "level": "INFO",
            "type": "security",
        }

        for record in caplog.records:
            event = json.loads(record.msg)
            assert event.pop("datetime")
            assert expected_value == event


class TestSystemShutdownEvent:
    """Tests for sec_log_system_shutdown function."""

    @pytest.mark.parametrize(
        "mode,delay,message,expected_event,expected_descr",
        [
            pytest.param(
                "poweroff",
                "+5",
                "",
                "sys_shutdown:cloud-init",
                "System shutdown initiated",
                id="poweroff_with_delay",
            ),
            pytest.param(
                "reboot",
                "now",
                None,
                "sys_restart:cloud-init",
                "System restart initiated",
                id="reboot_immediate",
            ),
            pytest.param(
                "reboot",
                "now",
                "Restart FTW",
                "sys_restart:cloud-init",
                "System restart initiated: Restart FTW",
                id="reboot_immediate",
            ),
        ],
    )
    def test_logs_system_shutdown_event(
        self,
        mode,
        delay,
        message,
        expected_event,
        expected_descr,
        caplog,
    ):
        """Test logging a system shutdown event."""

        class DecoratedShutDownTest:
            @classmethod
            @sec_log_system_shutdown
            def shutdown_test(cls, mode, delay, message):
                pass

        method_test = DecoratedShutDownTest()

        with caplog.at_level(loggers.SECURITY):
            method_test.shutdown_test(
                mode=mode,
                delay=delay,
                message=message,
            )

        event = json.loads(caplog.records[0].msg)
        assert event.pop("datetime")
        expected = {
            "appid": "canonical.cloud-init",
            "delay": delay,
            "description": expected_descr,
            "event": expected_event,
            "hostname": get_hostname(),
            "level": "INFO",
            "mode": "reboot",
            "type": "security",
        }
        if mode != "reboot":
            expected["mode"] = mode
        assert expected == event


class TestEventTypeEnums:
    """Tests for event type enum values."""

    @pytest.mark.parametrize(
        "event_type,expected_value",
        [
            pytest.param(
                OWASPEventType.AUTHN_PASSWORD_CHANGE,
                "authn_password_change",
                id="authn_password_change",
            ),
            pytest.param(
                OWASPEventType.SYS_SHUTDOWN, "sys_shutdown", id="sys_shutdown"
            ),
            pytest.param(
                OWASPEventType.SYS_RESTART, "sys_restart", id="sys_restart"
            ),
            pytest.param(
                OWASPEventType.USER_CREATED, "user_created", id="user_created"
            ),
        ],
    )
    def test_event_type_values(self, event_type, expected_value):
        """Test event type enum values."""
        assert event_type.value == expected_value
