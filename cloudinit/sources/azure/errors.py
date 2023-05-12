# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import csv
import logging
import traceback
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

from cloudinit import version
from cloudinit.sources.azure import identity

LOG = logging.getLogger(__name__)


def encode_report(
    data: List[str], delimiter: str = "|", quotechar: str = "'"
) -> str:
    """Encode report data with csv."""
    with StringIO() as io:
        csv.writer(
            io,
            delimiter=delimiter,
            quotechar=quotechar,
            quoting=csv.QUOTE_MINIMAL,
        ).writerow(data)

        # strip trailing \r\n
        return io.getvalue().rstrip()


class ReportableError(Exception):
    def __init__(
        self,
        reason: str,
        *,
        supporting_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.agent = f"Cloud-Init/{version.version_string()}"
        self.documentation_url = "https://aka.ms/linuxprovisioningerror"
        self.reason = reason

        if supporting_data:
            self.supporting_data = supporting_data
        else:
            self.supporting_data = {}

        self.timestamp = datetime.utcnow()

        try:
            self.vm_id = identity.query_vm_id()
        except Exception as id_error:
            self.vm_id = f"failed to read vm id: {id_error!r}"

    def as_encoded_report(
        self,
    ) -> str:
        data = [
            "result=error",
            f"reason={self.reason}",
            f"agent={self.agent}",
        ]
        data += [f"{k}={v}" for k, v in self.supporting_data.items()]
        data += [
            f"vm_id={self.vm_id}",
            f"timestamp={self.timestamp.isoformat()}",
            f"documentation_url={self.documentation_url}",
        ]

        return encode_report(data)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, ReportableError)
            and self.timestamp == other.timestamp
            and self.reason == other.reason
            and self.supporting_data == other.supporting_data
        )

    def __repr__(self) -> str:
        return self.as_encoded_report()


class ReportableErrorUnhandledException(ReportableError):
    def __init__(self, exception: Exception) -> None:
        super().__init__("unhandled exception")

        trace = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        trace_base64 = base64.b64encode(trace.encode("utf-8")).decode("utf-8")

        self.supporting_data["exception"] = repr(exception)
        self.supporting_data["traceback_base64"] = trace_base64
