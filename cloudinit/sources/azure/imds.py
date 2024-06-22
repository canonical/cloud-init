# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import uuid
from time import monotonic
from typing import Dict, Optional, Type, Union

import requests

from cloudinit import util
from cloudinit.sources.helpers.azure import report_diagnostic_event
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)

IMDS_URL = "http://169.254.169.254/metadata"


def headers_cb(_url):
    return {
        "Metadata": "true",
        "x-ms-client-request-id": str(uuid.uuid4()),
    }


class ReadUrlRetryHandler:
    """Manager for readurl retry behavior using exception_callback().

    :param logging_backoff: Backoff to limit logging.
    :param max_connection_errors: Number of connection errors to retry on.
    :param retry_codes: Set of http codes to retry on.
    :param retry_deadline: Optional monotonic()-based deadline to retry until.
    """

    def __init__(
        self,
        *,
        logging_backoff: float = 1.0,
        max_connection_errors: Optional[int] = None,
        retry_codes=(
            404,  # not found (yet)
            410,  # gone / unavailable (yet)
            429,  # rate-limited/throttled
            500,  # server error
        ),
        retry_deadline: Optional[float] = None,
    ) -> None:
        self.logging_backoff = logging_backoff
        self.max_connection_errors = max_connection_errors
        self.retry_codes = retry_codes
        self.retry_deadline = retry_deadline
        self._logging_threshold = 1.0
        self._request_count = 0
        self._last_error: Union[None, Type, int] = None

    def exception_callback(self, req_args, exception) -> bool:
        self._request_count += 1
        if not isinstance(exception, UrlError):
            report_diagnostic_event(
                "Polling IMDS failed with unexpected exception: %r"
                % (exception),
                logger_func=LOG.warning,
            )
            return False

        log = True
        if (
            self.retry_deadline is not None
            and monotonic() >= self.retry_deadline
        ):
            retry = False
        else:
            retry = True

        # Check for connection errors which may occur early boot, but
        # are otherwise indicative that we are not connecting with the
        # primary NIC.
        if self.max_connection_errors is not None and isinstance(
            exception.cause, requests.ConnectionError
        ):
            self.max_connection_errors -= 1
            if self.max_connection_errors <= 0:
                retry = False
        elif (
            exception.code is not None
            and exception.code not in self.retry_codes
        ):
            retry = False

        if self._request_count >= self._logging_threshold:
            self._logging_threshold *= self.logging_backoff
        else:
            log = False

        # Always log if error does not match previous.
        if exception.code is not None:
            # This is an HTTP response with failing code, log if different.
            if self._last_error != exception.code:
                log = True
                self._last_error = exception.code
        elif (
            # No previous error to match against.
            self._last_error is None
            # Previous error is exception code (int).
            or not isinstance(self._last_error, type)
            # Previous error is different class.
            or not isinstance(exception.cause, self._last_error)
        ):
            log = True
            self._last_error = type(exception.cause)

        if log or not retry:
            report_diagnostic_event(
                "Polling IMDS failed attempt %d with exception: %r"
                % (self._request_count, exception),
                logger_func=LOG.warning,
            )
        return retry


def _fetch_url(
    url: str,
    *,
    retry_handler: ReadUrlRetryHandler,
    log_response: bool = True,
    timeout: int = 30,
) -> bytes:
    """Fetch URL from IMDS.

    :param url: url to fetch.
    :param log_response: log responses in readurl().
    :param retry_deadline: time()-based deadline to retry until.
    :param timeout: Read/connection timeout in seconds for readurl().

    :raises UrlError: on error fetching metadata.
    """
    try:
        response = readurl(
            url,
            exception_cb=retry_handler.exception_callback,
            headers_cb=headers_cb,
            infinite=True,
            log_req_resp=log_response,
            timeout=timeout,
        )
    except UrlError as error:
        report_diagnostic_event(
            "Failed to fetch metadata from IMDS: %s" % error,
            logger_func=LOG.warning,
        )
        raise

    return response.contents


def _fetch_metadata(
    url: str,
    *,
    retry_handler: ReadUrlRetryHandler,
) -> Dict:
    """Fetch IMDS metadata.

    :param url: url to fetch.
    :param retry_deadline: time()-based deadline to retry until.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    metadata = _fetch_url(url, retry_handler=retry_handler)

    try:
        return util.load_json(metadata.decode("utf-8"))
    except ValueError as error:
        report_diagnostic_event(
            "Failed to parse metadata from IMDS: %s" % error,
            logger_func=LOG.warning,
        )
        raise


def fetch_metadata_with_api_fallback(
    retry_deadline: float, max_connection_errors: Optional[int] = None
) -> Dict:
    """Fetch extended metadata, falling back to non-extended as required.

    :param retry_deadline: time()-based deadline to retry until.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    retry_handler = ReadUrlRetryHandler(
        max_connection_errors=max_connection_errors,
        retry_deadline=retry_deadline,
    )
    try:
        url = IMDS_URL + "/instance?api-version=2021-08-01&extended=true"
        return _fetch_metadata(url, retry_handler=retry_handler)
    except UrlError as error:
        if error.code == 400:
            report_diagnostic_event(
                "Falling back to IMDS api-version: 2019-06-01",
                logger_func=LOG.warning,
            )
            retry_handler = ReadUrlRetryHandler(
                max_connection_errors=max_connection_errors,
                retry_deadline=retry_deadline,
            )
            url = IMDS_URL + "/instance?api-version=2019-06-01"
            return _fetch_metadata(url, retry_handler=retry_handler)
        raise


def fetch_reprovision_data() -> bytes:
    """Fetch extended metadata, falling back to non-extended as required.

    :raises UrlError: on error.
    """
    url = IMDS_URL + "/reprovisiondata?api-version=2019-06-01"

    handler = ReadUrlRetryHandler(
        logging_backoff=2.0,
        max_connection_errors=1,
        retry_codes=(
            404,
            410,
            429,
        ),
        retry_deadline=None,
    )
    response = readurl(
        url,
        exception_cb=handler.exception_callback,
        headers_cb=headers_cb,
        infinite=True,
        log_req_resp=False,
        timeout=30,
    )

    report_diagnostic_event(
        f"Polled IMDS {handler._request_count+1} time(s)",
        logger_func=LOG.debug,
    )
    return response.contents
