# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import base64
import csv
import logging
import traceback
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

import requests

from cloudinit import version
from cloudinit.sources.azure import identity
from cloudinit.url_helper import UrlError

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
        return (
            f"{self.__class__.__name__}("
            f"reason={self.reason}, "
            f"timestamp={self.timestamp}, "
            f"supporting_data={self.supporting_data})"
        )


class ReportableErrorDhcpInterfaceNotFound(ReportableError):
    def __init__(self, duration: float) -> None:
        super().__init__("failure to find DHCP interface")

        self.supporting_data["duration"] = duration


class ReportableErrorDhcpLease(ReportableError):
    def __init__(self, duration: float, interface: Optional[str]) -> None:
        super().__init__("failure to obtain DHCP lease")

        self.supporting_data["duration"] = duration
        self.supporting_data["interface"] = interface


class ReportableErrorDhcpOnNonPrimaryInterface(ReportableError):
    def __init__(
        self,
        *,
        interface: Optional[str],
        driver: Optional[str],
        router: Optional[str],
        static_routes: Optional[List[Tuple[str, str]]],
        lease: Dict[str, Any],
    ) -> None:
        super().__init__("failure to find primary DHCP interface")

        self.supporting_data["interface"] = interface
        self.supporting_data["driver"] = driver
        self.supporting_data["router"] = router
        self.supporting_data["static_routes"] = static_routes
        self.supporting_data["lease"] = lease


class ReportableErrorImdsUrlError(ReportableError):
    def __init__(self, *, exception: UrlError, duration: float) -> None:
        # ConnectTimeout sub-classes ConnectError so order is important.
        if isinstance(exception.cause, requests.ConnectTimeout):
            reason = "connection timeout querying IMDS"
        elif isinstance(exception.cause, requests.ConnectionError):
            reason = "connection error querying IMDS"
        elif isinstance(exception.cause, requests.ReadTimeout):
            reason = "read timeout querying IMDS"
        elif exception.code:
            reason = f"http error {exception.code} querying IMDS"
        else:
            reason = "unexpected error querying IMDS"

        super().__init__(reason)

        if exception.code:
            self.supporting_data["http_code"] = exception.code

        self.supporting_data["duration"] = duration
        self.supporting_data["exception"] = repr(exception)
        self.supporting_data["url"] = exception.url


class ReportableErrorImdsInvalidMetadata(ReportableError):
    def __init__(self, *, key: str, value: Any) -> None:
        super().__init__(f"invalid IMDS metadata for key={key}")

        self.supporting_data["key"] = key
        self.supporting_data["value"] = repr(value)


class ReportableErrorImdsMetadataParsingException(ReportableError):
    def __init__(self, *, exception: ValueError) -> None:
        super().__init__("error parsing IMDS metadata")

        self.supporting_data["exception"] = repr(exception)


class ReportableErrorOsDiskPpsFailure(ReportableError):
    def __init__(self) -> None:
        super().__init__("error waiting for host shutdown")


class ReportableErrorOvfInvalidMetadata(ReportableError):
    def __init__(self, message: str) -> None:
        super().__init__(f"unexpected metadata parsing ovf-env.xml: {message}")


class ReportableErrorOvfParsingException(ReportableError):
    def __init__(self, *, exception: ElementTree.ParseError) -> None:
        message = exception.msg
        super().__init__(f"error parsing ovf-env.xml: {message}")


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
