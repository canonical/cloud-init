# This file is part of cloud-init. See LICENSE file for license information.

"""
OWASP-formatted Security Event Logging for cloud-init.

This module provides security event logging following the OWASP Logging
Vocabulary Cheat Sheet:
https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Logging_Vocabulary_Cheat_Sheet.md

Security events are logged in JSON Lines format with standardized fields:
- datetime: ISO 8601 timestamp with UTC offset
- appid: Application identifier (canonical.cloud_init)
- event: Event type with optional parameters (e.g., user_created:root,ubuntu)
- level: INFO, WARN, or CRITICAL
- description: Human-readable summary
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

# Hard-coded application identifier per spec
APP_ID = "canonical.cloud_init"


class OWASPEventLevel(Enum):
    """Log levels per OWASP recommendations."""

    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


class OWASPEventType(Enum):
    """
    OWASP security event types.

    Format: category_event_name
    Events are logged as: event_type:param1,param2,...
    """

    # Authentication events [AUTHN]
    AUTHN_PASSWORD_CHANGE = "authn_password_change"

    # System events [SYS]
    SYS_SHUTDOWN = "sys_shutdown"
    SYS_RESTART = "sys_restart"

    # User management events [USER]
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"


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
        "event": _build_event_string(event_type, event_params),
        "level": level.value,
        "description": description,
        "hostname": util.get_hostname(),
    }

    if additional_data:
        # Merge additional data but don't overwrite core fields
        for key, value in additional_data.items():
            if key not in event:
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
    """
    A decorator to log a user creation event and priviledged attributes.

    :param userid: The user/process that initiated the action.
    :param new_userid: The username of the newly created user.
    :param attributes: Additional user attributes (groups, shell, etc.).
    """

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        new_userid = args[-1] if args else kwargs.get("name")
        if not new_userid:
            raise RuntimeError(
                "sec_log_user_created requires positional param name or kwarg"
            )
        params = ["cloud-init", new_userid]

        response = func(*args, **kwargs)
        if response:
            _log_security_event(
                event_type=OWASPEventType.USER_CREATED,
                level=OWASPEventLevel.WARN,
                description=f"User '{new_userid}' was created",
                event_params=params,
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
            userid = args[-1]
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
    def decorator(*args, **kwargs):
        mode = kwargs["mode"]
        delay = kwargs["delay"]

        additional = {}
        if mode == "reboot":
            event_type = OWASPEventType.SYS_RESTART
            description = "System restart initiated"
        else:
            event_type = OWASPEventType.SYS_SHUTDOWN
            description = f"System shutdown initiated (mode={mode})"
            additional["mode"] = mode
        if delay:
            additional["delay"] = delay

        _log_security_event(
            event_type=event_type,
            level=OWASPEventLevel.INFO,
            description=description,
            event_params=["cloud-init"],
            additional_data=additional if additional else None,
        )
        return func(*args, **kwargs)

    return decorator
