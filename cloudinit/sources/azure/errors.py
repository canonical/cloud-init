# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import csv
import logging
import traceback
from datetime import datetime
from io import StringIO
from typing import Any, Dict, Optional

from cloudinit import version

from .dmi import query_vm_id

LOG = logging.getLogger(__name__)


class ReportableError(Exception):
    def __init__(
        self,
        reason: str,
        *,
        supporting_data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        self.documentation_url = "https://aka.ms/linuxprovisioningerror"
        self.error = "PROVISIONING_FAILED_CLOUDINIT"
        self.reason = reason

        if supporting_data:
            self.supporting_data = supporting_data
        else:
            self.supporting_data = {}

        if timestamp:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.utcnow()

    def as_description(
        self, *, delimiter: str = "|", quotechar: str = "'"
    ) -> str:
        error = [
            f"error={self.error}",
            f"reason={self.reason}",
            f"agent=Cloud-Init/{version.version_string()}",
            f"documentation_url={self.documentation_url}",
            f"timestamp={self.timestamp.isoformat()}",
        ]

        vm_id = query_vm_id()
        if vm_id:
            error.append(f"vm_id={vm_id}")

        data = error + [f"{k}={v}" for k, v in self.supporting_data.items()]

        with StringIO() as io:
            csv.writer(
                io,
                delimiter=delimiter,
                quotechar=quotechar,
                quoting=csv.QUOTE_MINIMAL,
            ).writerow(data)

            # strip trailing \r\n
            csv_data = io.getvalue()[:-2]

        return f"PROVISIONING_ERROR: {csv_data}"

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, ReportableError)
            and self.timestamp == other.timestamp
            and self.reason == other.reason
            and self.supporting_data == other.supporting_data
        )

    def __repr__(self) -> str:
        return self.as_description()


class ReportableErrorUnhandledException(ReportableError):
    def __init__(self, exception: Exception) -> None:
        super().__init__("unhandled exception")

        trace = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        trace_base64 = base64.b64encode(trace.encode("utf-8"))

        self.supporting_data["exception"] = repr(exception)
        self.supporting_data["traceback_base64"] = trace_base64
