# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

from typing import Dict

import requests

from cloudinit import log as logging
from cloudinit import util
from cloudinit.sources.helpers.azure import report_diagnostic_event
from cloudinit.url_helper import UrlError, readurl

LOG = logging.getLogger(__name__)

IMDS_URL = "http://169.254.169.254/metadata"


class ReadUrlRetryHandler:
    def __init__(
        self,
        *,
        retry_codes=(
            404,  # not found (yet)
            410,  # gone / unavailable (yet)
            429,  # rate-limited/throttled
            500,  # server error
        ),
        max_connection_errors: int = 10,
        logging_backoff: float = 1.0,
    ) -> None:
        self.logging_backoff = logging_backoff
        self.max_connection_errors = max_connection_errors
        self.retry_codes = retry_codes
        self._logging_threshold = 1.0
        self._request_count = 0

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
        retry = True

        # Check for connection errors which may occur early boot, but
        # are otherwise indicative that we are not connecting with the
        # primary NIC.
        if isinstance(
            exception.cause, (requests.ConnectionError, requests.Timeout)
        ):
            self.max_connection_errors -= 1
            if self.max_connection_errors < 0:
                retry = False
        elif exception.code not in self.retry_codes:
            retry = False

        if self._request_count >= self._logging_threshold:
            self._logging_threshold *= self.logging_backoff
        else:
            log = False

        if log or not retry:
            report_diagnostic_event(
                "Polling IMDS failed attempt %d with exception: %r"
                % (self._request_count, exception),
                logger_func=LOG.info,
            )
        return retry


def _fetch_url(
    url: str, *, log_response: bool = True, retries: int = 10, timeout: int = 2
) -> bytes:
    """Fetch URL from IMDS.

    :raises UrlError: on error fetching metadata.
    """
    handler = ReadUrlRetryHandler()

    try:
        response = readurl(
            url,
            exception_cb=handler.exception_callback,
            headers={"Metadata": "true"},
            infinite=False,
            log_req_resp=log_response,
            retries=retries,
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
    retries: int = 10,
) -> Dict:
    """Fetch IMDS metadata.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    metadata = _fetch_url(url, retries=retries)

    try:
        return util.load_json(metadata)
    except ValueError as error:
        report_diagnostic_event(
            "Failed to parse metadata from IMDS: %s" % error,
            logger_func=LOG.warning,
        )
        raise


def fetch_metadata_with_api_fallback(retries: int = 10) -> Dict:
    """Fetch extended metadata, falling back to non-extended as required.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    try:
        url = IMDS_URL + "/instance?api-version=2021-08-01&extended=true"
        return _fetch_metadata(url, retries=retries)
    except UrlError as error:
        if error.code == 400:
            report_diagnostic_event(
                "Falling back to IMDS api-version: 2019-06-01",
                logger_func=LOG.warning,
            )
            url = IMDS_URL + "/instance?api-version=2019-06-01"
            return _fetch_metadata(url, retries=retries)
        raise


def fetch_reprovision_data() -> bytes:
    """Fetch extended metadata, falling back to non-extended as required.

    :raises UrlError: on error.
    """
    url = IMDS_URL + "/reprovisiondata?api-version=2019-06-01"

    handler = ReadUrlRetryHandler(
        logging_backoff=2.0,
        max_connection_errors=0,
        retry_codes=(
            404,
            410,
        ),
    )
    response = readurl(
        url,
        exception_cb=handler.exception_callback,
        headers={"Metadata": "true"},
        infinite=True,
        log_req_resp=False,
        timeout=2,
    )

    report_diagnostic_event(
        f"Polled IMDS {handler._request_count+1} time(s)",
        logger_func=LOG.debug,
    )
    return response.contents
