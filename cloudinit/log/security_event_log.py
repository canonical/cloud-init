# This file is part of cloud-init. See LICENSE file for license information.

"""
OWASP-formatted Security Event Logging for cloud-init.

This module provides security event logging following the OWASP Logging
Vocabulary Cheat Sheet:
https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Logging_Vocabulary_Cheat_Sheet.md

Security events are logged in JSON Lines format with standardized fields:
- datetime: ISO 8601 timestamp with UTC offset
- appid: Application identifier (canonical.cloud-init)
- type: "security"
- event: Event type with optional parameters (e.g., user_created:root,ubuntu)
- level: INFO, WARN, or CRITICAL
- description: Human-readable summary
- host_ip: Optional IP address, included when network information is available.
"""

import functools
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from cloudinit import util
from cloudinit.log import loggers

LOG = logging.getLogger(__name__)

# Hard-coded application identifier
APP_ID = "canonical.cloud-init"


class OWASPEventLevel(Enum):
    """OWASP log levels."""

    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class OWASPEventType(Enum):
    """OWASP security event types."""

    # Authentication events [AUTHN]
    AUTHN_PASSWORD_CHANGE = "authn_password_change"

    # System events [SYS]
    SYS_SHUTDOWN = "sys_shutdown"
    SYS_RESTART = "sys_restart"

    # User management events [USER]
    USER_CREATED = "user_created"
    # TODO(USER_UPDATED = "user_updated")


def _log_security_event(
    event_type: OWASPEventType,
    level: OWASPEventLevel,
    description: str,
    event_params: Optional[List[str]] = None,
    additional_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a security event in OWASP format.

    :param event_type: Type of security event.
    :param level: OWASP Log level (INFO, WARN, CRITICAL).
    :param description: Human-readable description of the event.
    :param event_params: Parameters to include in the event string.
    :param additional_data: Additional context-specific data.
    """
    # cloud-init is the default primary 'actor' for any system change operation
    if event_params:
        event_params.insert(0, "cloud-init")
    else:
        event_params = ["cloud-init"]

    event_str = event_type.value
    if event_params:
        event_str += ":" + ",".join(event_params)
    event = {
        "appid": APP_ID,
        "type": "security",
        "event": event_str,
        "level": str(level.value),
        "description": description,
        "hostname": util.get_hostname(),
    }
    if additional_data:
        # Merge additional non-empty data but don't overwrite core fields
        for key, value in additional_data.items():
            if key not in event and value:
                event[key] = value

    LOG.log(loggers.SECURITY, event)


def sec_log_user_created(func):
    """A decorator to log a user creation event and group attributes."""

    @functools.wraps(func)
    def decorator(
        self, name: str, groups: Optional[List[str]] = None, *args, **kwargs
    ):
        if not name:
            raise RuntimeError(
                "sec_log_user_created requires positional param name or kwarg"
            )
        params = [name]
        groups_msg = ""
        if groups is None:
            groups = []
        all_groups = groups + self._get_elevated_roles(**kwargs)
        if all_groups:
            groups_suffix = ",".join(all_groups)
            groups_msg = f" in groups: {groups_suffix}"
            params.append(f"groups:{groups_suffix}")

        response = func(self, name, groups=groups, *args, **kwargs)
        # User creation operation did not raise an Exception
        _log_security_event(
            event_type=OWASPEventType.USER_CREATED,
            # Treat INFO level as this is prescribed provisioning at launch
            level=OWASPEventLevel.INFO,
            description=f"User '{name}' was created{groups_msg}",
            event_params=params,
        )
        return response

    return decorator


def sec_log_password_changed_batch(func):
    @functools.wraps(func)
    def decorator(self, plist_in: List[Tuple[str, str]], *args, **kwargs):
        response = func(self, plist_in, *args, **kwargs)
        for userid, _ in plist_in:
            _log_security_event(
                event_type=OWASPEventType.AUTHN_PASSWORD_CHANGE,
                level=OWASPEventLevel.INFO,
                description=f"Password changed for user '{userid}'",
                event_params=[userid],
            )
        return response

    return decorator


def sec_log_password_changed(func):
    """A decorator logging a password change event."""

    @functools.wraps(func)
    def decorator(self, user: str, *args, **kwargs):
        response = func(self, user, *args, **kwargs)
        _log_security_event(
            event_type=OWASPEventType.AUTHN_PASSWORD_CHANGE,
            level=OWASPEventLevel.INFO,
            description=f"Password changed for user '{user}'",
            event_params=[user],
        )
        return response

    return decorator


def sec_log_system_shutdown(func):
    """A decorator logging a system shutdown event."""

    @functools.wraps(func)
    def decorator(cls, mode: str, delay: str, message):
        if mode == "reboot":
            event_type = OWASPEventType.SYS_RESTART
            description = "System restart initiated"
        else:
            event_type = OWASPEventType.SYS_SHUTDOWN
            description = "System shutdown initiated"
        if message:
            description += f": {message}"

        _log_security_event(
            event_type=event_type,
            level=OWASPEventLevel.INFO,
            description=description,
            additional_data={"delay": delay, "mode": mode},
        )
        return func(cls, mode=mode, delay=delay, message=message)

    return decorator
