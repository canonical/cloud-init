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
import json
import logging
import os
import socket
from enum import Enum
from typing import Any, Dict, List, Optional

from cloudinit import util
from cloudinit.settings import DEFAULT_SECURITY_LOG

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
    log_file: Optional[str] = DEFAULT_SECURITY_LOG,
) -> None:
    """
    Log a security event in OWASP format.

    :param event_type: Type of security event.
    :param level: Log level (INFO, WARN, CRITICAL).
    :param description: Human-readable description of the event.
    :param event_params: Parameters to include in the event string.
    :param additional_data: Additional context-specific data.
    :param log_file: Path to which to write the JSON lines.
    """
    event = _build_security_event(
        event_type=event_type,
        level=level,
        description=description,
        event_params=event_params,
        additional_data=additional_data,
    )

    try:
        json_line = json.dumps(event, separators=(",", ":")) + "\n"

        # Create file with restricted permissions if it doesn't exist
        if not os.path.exists(log_file):
            util.ensure_file(log_file, mode=0o600, preserve_mode=False)

        util.append_file(log_file, json_line, disable_logging=True)

    except Exception as e:
        LOG.warning(
            "Failed to write security event to %s: %s",
            log_file,
            str(e),
        )


def sec_log_user_created(
    userid: str,
    new_userid: str,
    attributes: Optional[Dict[str, Any]] = None,
    log_file: Optional[str] = DEFAULT_SECURITY_LOG,
) -> None:
    """
    Log a user creation event providing any admin-related attributes granted.

    :param userid: The user/process that initiated the action.
    :param new_userid: The username of the newly created user.
    :param attributes: Additional user attributes (groups, shell, etc.).
    :param log_file: Override the default log file path.
    """
    params = [userid, new_userid]
    if attributes:
        # Add a summary of attributes
        attr_summary = ";".join(
            f"{k}={v}" for k, v in attributes.items() if v is not None
        )
        if attr_summary:
            params.append(attr_summary)

    _log_security_event(
        event_type=OWASPEventType.USER_CREATED,
        level=OWASPEventLevel.WARN,
        description=f"User '{new_userid}' was created",
        event_params=params,
        additional_data=attributes,
        log_file=log_file,
    )


def sec_log_user_updated(
    userid: str,
    on_userid: str,
    attributes: Optional[Dict[str, Any]] = None,
    log_file: Optional[str] = DEFAULT_SECURITY_LOG,
) -> None:
    """
    Log a user update event.

    :param userid: The user/process that initiated the action.
    :param on_userid: The username being updated.
    :param attributes: Attributes being updated.
    :param log_file: Override the default log file path.
    """
    params = [userid, on_userid]
    if attributes:
        attr_summary = ";".join(
            f"{k}={v}" for k, v in attributes.items() if v is not None
        )
        if attr_summary:
            params.append(attr_summary)

    _log_security_event(
        event_type=OWASPEventType.USER_UPDATED,
        level=OWASPEventLevel.WARN,
        description=f"User '{on_userid}' was updated",
        event_params=params,
        additional_data=attributes,
        log_file=log_file,
    )


def sec_log_password_changed(
    userid: str,
    log_file: Optional[str] = DEFAULT_SECURITY_LOG,
) -> None:
    """
    Log a password change event.

    :param userid: The user whose password was changed.
    :param log_file: Override the default log file path.
    """
    _log_security_event(
        event_type=OWASPEventType.AUTHN_PASSWORD_CHANGE,
        level=OWASPEventLevel.INFO,
        description=f"Password changed for user '{userid}'",
        event_params=[userid],
        log_file=log_file,
    )


def sec_log_system_shutdown(
    userid: Optional[str] = None,
    mode: Optional[str] = None,
    delay: Optional[str] = None,
    log_file: Optional[str] = DEFAULT_SECURITY_LOG,
) -> None:
    """
    Log a system shutdown event.

    :param userid: The user/process that initiated the shutdown.
    :param mode: Shutdown mode (halt, poweroff, reboot).
    :param delay: Delay before shutdown.
    :param log_file: Override the default log file path.
    """
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
        event_type=OWASPEventType.SYS_SHUTDOWN,
        level=OWASPEventLevel.INFO,
        description=f"System shutdown initiated (mode={mode})",
        event_params=["cloud-init"],
        additional_data=additional if additional else None,
        log_file=log_file,
    )
