# Copyright (C) 2022 Microsoft Corporation.
#
# This file is part of cloud-init. See LICENSE file for license information.

import functools
from typing import Dict

import requests

from cloudinit import log as logging
from cloudinit import util
from cloudinit.sources.helpers.azure import report_diagnostic_event
from cloudinit.url_helper import UrlError, readurl, retry_on_url_exc

LOG = logging.getLogger(__name__)

IMDS_URL = "http://169.254.169.254/metadata"

_readurl_exception_callback = functools.partial(
    retry_on_url_exc,
    retry_codes=(
        404,  # not found (yet)
        410,  # gone / unavailable (yet)
        429,  # rate-limited/throttled
        500,  # server error
    ),
    retry_instances=(
        requests.ConnectionError,
        requests.Timeout,
    ),
)


def _fetch_url(
    url: str, *, log_response: bool = True, retries: int = 10, timeout: int = 2
) -> bytes:
    """Fetch URL from IMDS.

    :raises UrlError: on error fetching metadata.
    """

    try:
        response = readurl(
            url,
            exception_cb=_readurl_exception_callback,
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
) -> Dict:
    """Fetch IMDS metadata.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    metadata = _fetch_url(url)

    try:
        return util.load_json(metadata)
    except ValueError as error:
        report_diagnostic_event(
            "Failed to parse metadata from IMDS: %s" % error,
            logger_func=LOG.warning,
        )
        raise


def fetch_metadata_with_api_fallback() -> Dict:
    """Fetch extended metadata, falling back to non-extended as required.

    :raises UrlError: on error fetching metadata.
    :raises ValueError: on error parsing metadata.
    """
    try:
        url = IMDS_URL + "/instance?api-version=2021-08-01&extended=true"
        return _fetch_metadata(url)
    except UrlError as error:
        if error.code == 400:
            report_diagnostic_event(
                "Falling back to IMDS api-version: 2019-06-01",
                logger_func=LOG.warning,
            )
            url = IMDS_URL + "/instance?api-version=2019-06-01"
            return _fetch_metadata(url)
        raise


def fetch_reprovision_data() -> bytes:
    """Fetch extended metadata, falling back to non-extended as required.

    :raises UrlError: on error.
    """
    url = IMDS_URL + "/reprovisiondata?api-version=2019-06-01"

    logging_threshold = 1
    poll_counter = 0

    def exception_callback(msg, exception):
        nonlocal logging_threshold
        nonlocal poll_counter

        poll_counter += 1
        if not isinstance(exception, UrlError):
            report_diagnostic_event(
                "Polling IMDS failed with unexpected exception: %r"
                % (exception),
                logger_func=LOG.warning,
            )
            return False

        log = True
        retry = False
        if exception.code in (404, 410):
            retry = True
            if poll_counter >= logging_threshold:
                # Exponential back-off on logging.
                logging_threshold *= 2
            else:
                log = False

        if log:
            report_diagnostic_event(
                "Polling IMDS failed with exception: %r count: %d"
                % (exception, poll_counter),
                logger_func=LOG.info,
            )
        return retry

    response = readurl(
        url,
        exception_cb=exception_callback,
        headers={"Metadata": "true"},
        infinite=True,
        log_req_resp=False,
        timeout=2,
    )

    report_diagnostic_event(
        f"Polled IMDS {poll_counter+1} time(s)",
        logger_func=LOG.debug,
    )
    return response.contents
