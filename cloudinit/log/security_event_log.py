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

import datetime
import functools
import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

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


def _build_event_string(
    event_type: OWASPEventType, params: Optional[List[str]] = None
) -> str:
    """
    Build the OWASP event string with optional parameters.

    :param event_type: The type of security event.
    :param params: Optional list of parameters to append.
    :return: Event string in format "event_type:param1,param2,..."
    """
    event_str = event_type.value
    if params:
        # Filter out None values and convert to strings
        filtered_params = [str(p) for p in params if p is not None]
        if filtered_params:
            event_str += ":" + ",".join(filtered_params)
    return event_str


def _build_security_event(
    event_type: OWASPEventType,
    level: OWASPEventLevel,
    description: str,
    event_params: Optional[List[str]] = None,
    additional_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a security event dictionary following OWASP Logging Vocabulary.

    :param event_type: Type of security event.
    :param level: Log level (INFO, WARN, CRITICAL).
    :param description: Human-readable description of the event.
    :param event_params: Parameters to include in the event string.
    :param additional_data: Additional context-specific data.
    :return: Dictionary containing the security event data.
    """
    event = {
        "datetime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "appid": APP_ID,
        "type": "security",
        "event": _build_event_string(event_type, event_params),
        "level": level.value,
        "description": description,
        "hostname": util.get_hostname(),
    }
    if additional_data:
        # Merge additional non-empty data but don't overwrite core fields
        for key, value in additional_data.items():
            if key not in event and value:
                event[key] = value

    return event


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
    event = _build_security_event(
        event_type=event_type,
        level=level,
        description=description,
        event_params=event_params,
        additional_data=additional_data,
    )
    LOG.log(loggers.SECURITY, json.dumps(event, separators=(",", ":")))


def sec_log_user_created(func):
    """A decorator to log a user creation event and group attributes."""

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        new_userid = args[-1] if args else kwargs.get("name")
        if not new_userid:
            raise RuntimeError(
                "sec_log_user_created requires positional param name or kwarg"
            )
        params = ["cloud-init", new_userid]
        groups_msg = ""
        groups_suffix = kwargs.get("groups", "")
        if groups_suffix:
            if isinstance(groups_suffix, (dict, list)):
                groups_suffix = ",".join(groups_suffix)
        for perms in ("sudo", "doas"):
            if kwargs.get(perms):
                groups_suffix += f",{perms}"
        if groups_suffix:
            groups_suffix = groups_suffix.strip(",")
            groups_msg = f" in groups: {groups_suffix}"
            params.append(f"groups:{groups_suffix}")

        response = func(*args, **kwargs)
        # User creation operation did not raise an Exception
        _log_security_event(
            event_type=OWASPEventType.USER_CREATED,
            level=OWASPEventLevel.WARN,
            description=f"User '{new_userid}' was created{groups_msg}",
            event_params=params,
        )
        return response

    return decorator


def sec_log_password_changed_batch(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        response = func(*args, **kwargs)
        plist_in = kwargs.get("plist_in")
        if not plist_in:
            plist_in = args[1]
        for userid, _ in plist_in:
            _log_security_event(
                event_type=OWASPEventType.AUTHN_PASSWORD_CHANGE,
                level=OWASPEventLevel.INFO,
                description=f"Password changed for user '{userid}'",
                event_params=["cloud-init", userid],
            )
        return response

    return decorator


def sec_log_password_changed(func):
    """A decorator logging a password change event."""

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        response = func(*args, **kwargs)
        userid = kwargs.get("user")
        if not userid:
            userid = args[1]
        _log_security_event(
            event_type=OWASPEventType.AUTHN_PASSWORD_CHANGE,
            level=OWASPEventLevel.INFO,
            description=f"Password changed for user '{userid}'",
            event_params=["cloud-init", userid],
        )
        return response

    return decorator


def sec_log_system_shutdown(func):
    """A decorator logging a system shutdown event."""

    @functools.wraps(func)
    def decorator(cls, mode, delay, message):
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
            event_params=["cloud-init"],
            additional_data={"delay": delay, "mode": mode},
        )
        return func(cls, mode=mode, delay=delay, message=message)

    return decorator
