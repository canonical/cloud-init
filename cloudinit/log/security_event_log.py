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
- hostname: System hostname
"""

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


def log_security_event(
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
    params = ["cloud-init"]
    if event_params:
        params.extend(event_params)
    event_str = f"{event_type.value}:{','.join(params)}"
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
        event.update(
            {k: v for k, v in additional_data.items() if v and k not in event}
        )
    LOG.log(loggers.SECURITY, event)
