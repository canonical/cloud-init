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


@pytest.fixture
def host_ip(mocker):
    mocker.patch.object(
        security_event_log, "_get_host_ip", return_value="10.42.42.42"
    )
    yield


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

    def test_event_contains_required_owasp_fields(self, host_ip):
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

    def test_event_with_additional_data(self, host_ip):
        """Test event includes additional data when provided."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"groups": "wheel", "shell": "/bin/bash"},
        )

        assert event["groups"] == "wheel"
        assert event["shell"] == "/bin/bash"

    def test_additional_data_does_not_overwrite_core_fields(self, host_ip):
        """Test that additional data cannot overwrite core fields."""
        event = security_event_log._build_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.INFO,
            description="Test event",
            additional_data={"appid": "malicious.app", "level": "CRITICAL"},
        )

        assert event["appid"] == "canonical.cloud-init"
        assert event["level"] == "INFO"

    def test_timestamp_is_iso_format(self, host_ip):
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

    def test_writes_json_to_file(self, host_ip, caplog):
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

    def test_appends_multiple_events(self, host_ip, caplog):
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
        self, uc_kwargs, event_id, description, host_ip, caplog
    ):
        """Test logging a user creation event."""

        @sec_log_user_created
        def user_created_decorator_test(name, **kwargs):
            return

        with caplog.at_level(loggers.SECURITY):
            user_created_decorator_test(
                name="testuser",
                **uc_kwargs,
            )

        event = json.loads(caplog.records[0].msg)

        assert event.pop("datetime")
        assert {
            "appid": "canonical.cloud-init",
            "event": event_id,
            "description": description,
            "host_ip": "10.42.42.42",
            "hostname": get_hostname(),
            "level": "WARN",
            "type": "security",
        } == event


class TestPasswordChangedEvent:
    """Tests for sec_log_password_changed function."""

    def test_logs_password_changed_event(self, host_ip, caplog):
        """Test logging a password change event."""

        @sec_log_password_changed
        def set_passwd_test(user):
            pass

        with caplog.at_level(loggers.SECURITY):
            set_passwd_test(user="testuser")
            set_passwd_test("testuser")  # Test with positional params

        expected_value = {
            "appid": "canonical.cloud-init",
            "event": "authn_password_change:cloud-init,testuser",
            "description": "Password changed for user 'testuser'",
            "host_ip": "10.42.42.42",
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

    def test_logs_password_changed_event_for_each_user(self, host_ip, caplog):
        """Test logging a password change event."""

        @sec_log_password_changed_batch
        def set_passwd_test(plist_in):
            pass

        with caplog.at_level(loggers.SECURITY):
            set_passwd_test(plist_in=(("testuser", "pw1"),))

        expected_value = {
            "appid": "canonical.cloud-init",
            "event": "authn_password_change:cloud-init,testuser",
            "description": "Password changed for user 'testuser'",
            "host_ip": "10.42.42.42",
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
        "mode,delay,expected_event,expected_descr",
        [
            pytest.param(
                "poweroff",
                "+5",
                "sys_shutdown:cloud-init",
                "System shutdown initiated (mode=poweroff)",
                id="poweroff_with_delay",
            ),
            pytest.param(
                "reboot",
                "now",
                "sys_restart:cloud-init",
                "System restart initiated",
                id="reboot_immediate",
            ),
        ],
    )
    def test_logs_system_shutdown_event(
        self, mode, delay, expected_event, expected_descr, host_ip, caplog
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
            "appid": "canonical.cloud-init",
            "delay": delay,
            "description": expected_descr,
            "event": expected_event,
            "host_ip": "10.42.42.42",
            "hostname": get_hostname(),
            "level": "INFO",
            "type": "security",
        }
        if mode != "reboot":
            expected["mode"] = mode
        assert expected == event


class TestGetHostIp:
    """Tests for _get_host_ip IPv4/IPv6 address resolution."""

    @pytest.mark.parametrize(
        "netdev_response,expected_ip",
        [
            pytest.param(
                {
                    "eth0": {
                        "up": True,
                        "ipv4": [{"ip": "10.0.0.1", "scope": "global"}],
                        "ipv6": [],
                    }
                },
                "10.0.0.1",
                id="global_ipv4",
            ),
            pytest.param(
                {
                    "eth0": {
                        "up": True,
                        "ipv4": [],
                        "ipv6": [
                            {"ip": "fd42::1/64", "scope6": "global"},
                            {"ip": "fe80::1/64", "scope6": "link"},
                        ],
                    }
                },
                "fd42::1",
                id="fallback_to_global_ipv6",
            ),
            pytest.param(
                {
                    "eth0": {
                        "up": True,
                        "ipv4": [],
                        "ipv6": [
                            {
                                "ip": "fd42:baa2:3dd:17a::1/64",
                                "scope6": "global",
                            }
                        ],
                    }
                },
                "fd42:baa2:3dd:17a::1",
                id="ipv6_prefix_stripped",
            ),
            pytest.param(
                {
                    "eth0": {
                        "up": True,
                        "ipv4": [{"ip": "10.0.0.1", "scope": "global"}],
                        "ipv6": [{"ip": "fd42::1/64", "scope6": "global"}],
                    }
                },
                "10.0.0.1",
                id="prefers_ipv4_over_ipv6",
            ),
            pytest.param(
                {
                    "lo": {
                        "up": True,
                        "ipv4": [{"ip": "127.0.0.1", "scope": "host"}],
                        "ipv6": [{"ip": "::1/128", "scope6": "host"}],
                    },
                    "eth0": {
                        "up": True,
                        "ipv4": [],
                        "ipv6": [{"ip": "fd42::1/64", "scope6": "global"}],
                    },
                },
                "fd42::1",
                id="skips_loopback",
            ),
            pytest.param(
                {
                    "eth0": {
                        "up": False,
                        "ipv4": [{"ip": "10.0.0.1", "scope": "global"}],
                        "ipv6": [{"ip": "fd42::1/64", "scope6": "global"}],
                    }
                },
                None,
                id="skips_down_interfaces",
            ),
            pytest.param(
                {
                    "eth0": {
                        "up": True,
                        "ipv4": [],
                        "ipv6": [{"ip": "fe80::1/64", "scope6": "link"}],
                    }
                },
                None,
                id="ignores_link_local_ipv6",
            ),
            pytest.param(
                Exception("network unavailable"),
                None,
                id="exception_returns_none",
            ),
        ],
    )
    def test_get_host_ip(self, mocker, netdev_response, expected_ip):
        """Test _get_host_ip returns the correct IP address or None."""
        if isinstance(netdev_response, Exception):
            mocker.patch(MPATH + "netdev_info", side_effect=netdev_response)
        else:
            mocker.patch(MPATH + "netdev_info", return_value=netdev_response)
        assert security_event_log._get_host_ip() == expected_ip


class TestHostIpInSecurityEvent:
    """Tests that host_ip is correctly populated in logged security events."""

    @pytest.mark.parametrize(
        "host_ip",
        [
            pytest.param("10.0.0.1", id="ipv4"),
            pytest.param("fd42:baa2:3dd:17a:216:3eff:fe16:db54", id="ipv6"),
            pytest.param(None, id="no_network"),
        ],
    )
    def test_event_logs_host_ip(self, host_ip, mocker, caplog):
        """Security event records host_ip returned by _get_host_ip."""
        mocker.patch.object(
            security_event_log, "_get_host_ip", return_value=host_ip
        )
        with caplog.at_level(loggers.SECURITY):
            security_event_log._log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.INFO,
                description="test",
            )
        if host_ip is None:
            assert "host_ip" not in json.loads(caplog.records[0].msg)
        else:
            assert json.loads(caplog.records[0].msg)["host_ip"] == host_ip


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
