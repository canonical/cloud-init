# This file is part of cloud-init. See LICENSE file for license information.

"""Tests for cloudinit.log.security_event_log"""

import json
import logging
from datetime import datetime

import pytest

from cloudinit.log import loggers, security_event_log
from cloudinit.log.loggers import SecurityFormatter
from cloudinit.log.security_event_log import (
    OWASPEventLevel,
    OWASPEventType,
    sec_log_password_changed,
    sec_log_password_changed_batch,
    sec_log_system_shutdown,
    sec_log_user_created,
)
from cloudinit.util import get_hostname
from tests.unittests.util import MockDistro

MPATH = "cloudinit.log.security_event_log."


class TestBuildEventString:
    """Tests for _build_event_string function."""

    @pytest.mark.parametrize(
        "event_type,params,expected",
        [
            pytest.param(
                OWASPEventType.SYS_SHUTDOWN,
                None,
                "sys_shutdown:cloud-init",
                id="no_params",
            ),
            pytest.param(
                OWASPEventType.AUTHN_PASSWORD_CHANGE,
                ["testuser"],
                "authn_password_change:cloud-init,testuser",
                id="single_param",
            ),
            pytest.param(
                OWASPEventType.USER_CREATED,
                ["newuser", "groups:wheel"],
                "user_created:cloud-init,newuser,groups:wheel",
                id="multiple_params",
            ),
        ],
    )
    def test_event_string_formatting(
        self, event_type, params, expected, caplog
    ):
        """Test event string formatting with various parameter combinations."""
        security_event_log._log_security_event(
            event_type=event_type,
            level=OWASPEventLevel.WARN,
            description="Test Descr",
            event_params=params,
        )
        event = caplog.records[0].msg
        assert event["appid"] == "canonical.cloud-init"
        assert event["level"] == "WARN"
        assert event["event"] == expected

    def test_additional_data_does_not_overwrite_core_fields(self, caplog):
        """Test that additional data cannot overwrite core fields."""
        security_event_log._log_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"appid": "malicious.app", "level": "CRITICAL"},
        )
        event = caplog.records[0].msg
        assert event["appid"] == "canonical.cloud-init"
        assert event["level"] == "INFO"


class TestLogSecurityEvent:
    """Tests for _log_security_event function."""

    def test_event_with_additional_data(self, caplog):
        """Test event includes additional data when provided."""
        security_event_log._log_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"groups": "wheel", "shell": "/bin/bash"},
        )
        event = caplog.records[0].msg
        assert event["groups"] == "wheel"
        assert event["shell"] == "/bin/bash"

    def test_writes_json_to_file(self, caplog):
        """Test that event is written to log file with OWASP fields."""
        with caplog.at_level(loggers.SECURITY):
            security_event_log._log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.INFO,
                description="User created successfully",
                event_params=["testuser"],
            )
        event = caplog.records[0].msg

        assert event["event"] == "user_created:cloud-init,testuser"
        assert event["level"] == "INFO"
        assert event["appid"] == "canonical.cloud-init"
        assert event["description"] == "User created successfully"
        assert "hostname" in event

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
        event1 = caplog.records[0].msg
        event2 = caplog.records[1].msg
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

        class DecoratedSetPasswordTest(MockDistro):

            @sec_log_user_created
            def user_created_decorator_test(self, name, **kwargs):
                return

        with caplog.at_level(loggers.SECURITY):
            DecoratedSetPasswordTest().user_created_decorator_test(
                name="testuser",
                **uc_kwargs,
            )

        assert {
            "appid": "canonical.cloud-init",
            "event": event_id,
            "description": description,
            "hostname": get_hostname(),
            "level": "INFO",
            "type": "security",
        } == caplog.records[0].msg


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
            assert expected_value == record.msg


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
            assert expected_value == record.msg


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
        assert expected == caplog.records[0].msg


class TestSecurityFormatter:
    """Tests for SecurityFormatter."""

    def _make_record(self, msg) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=loggers.SECURITY,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_injects_datetime_into_json_message(self):
        """Formatter adds 'datetime' and formats valid JSON messages."""
        record = self._make_record({"appid": "canonical.cloud-init"})
        result = json.loads(SecurityFormatter().format(record))
        assert "datetime" in result
        # ISO 8601: contains 'T' separator and UTC offset
        dt = datetime.utcfromtimestamp(record.created)
        expected_date = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+00:00"
        assert result["datetime"] == expected_date

    def test_errors_on_non_dict(self):
        """Non-Dict messages are returned unchanged."""
        record = self._make_record("not dict")
        with pytest.raises(
            ValueError, match="SECURITY logs expected dict but"
        ):
            SecurityFormatter().format(record)

    def test_datetime_uses_record_created_timestamp(self):
        """The injected datetime reflects the log record's creation time."""
        record = self._make_record({})
        result = json.loads(SecurityFormatter().format(record))
        dt = datetime.utcfromtimestamp(record.created)
        expected_date = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+00:00"
        assert result["datetime"] == expected_date


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
