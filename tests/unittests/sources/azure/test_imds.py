# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import math
import re
from unittest import mock

import pytest
import requests

from cloudinit.sources.azure import imds
from cloudinit.url_helper import UrlError, readurl

LOG_PATH = "cloudinit.sources.azure.imds"
MOCK_PATH = "cloudinit.sources.azure.imds."


class StringMatch:
    def __init__(self, regex) -> None:
        self.regex = regex

    def __eq__(self, other) -> bool:
        return bool(re.match("^" + self.regex + "$", other))


@pytest.fixture
def wrapped_readurl():
    with mock.patch.object(imds, "readurl", wraps=readurl) as m:
        yield m


@pytest.fixture
def mock_requests_session_request():
    with mock.patch("requests.Session.request", autospec=True) as m:
        yield m


@pytest.fixture
def mock_url_helper_time_sleep():
    with mock.patch("cloudinit.url_helper.time.sleep", autospec=True) as m:
        yield m


def fake_http_error_for_code(status_code: int):
    response_failure = requests.Response()
    response_failure.status_code = status_code
    return requests.exceptions.HTTPError(
        "fake error",
        response=response_failure,
    )


class TestFetchMetadataWithApiFallback:
    default_url = (
        "http://169.254.169.254/metadata/instance?"
        "api-version=2021-08-01&extended=true"
    )
    fallback_url = (
        "http://169.254.169.254/metadata/instance?api-version=2019-06-01"
    )
    headers = {"Metadata": "true"}
    retries = 10
    timeout = 2

    def test_basic(
        self,
        caplog,
        mock_requests_session_request,
        wrapped_readurl,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            mock.Mock(content=json.dumps(fake_md)),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=mock.ANY,
                infinite=False,
                log_req_resp=True,
            )
        ]
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    def test_basic_fallback(
        self,
        caplog,
        mock_requests_session_request,
        wrapped_readurl,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            UrlError("No IMDS version", code=400),
            mock.Mock(content=json.dumps(fake_md)),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=mock.ANY,
                infinite=False,
                log_req_resp=True,
            ),
            mock.call(
                self.fallback_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=mock.ANY,
                infinite=False,
                log_req_resp=True,
            ),
        ]

        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Failed to fetch metadata from IMDS: No IMDS version",
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Falling back to IMDS api-version: 2019-06-01",
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(404),
            fake_http_error_for_code(410),
            fake_http_error_for_code(429),
            fake_http_error_for_code(500),
            requests.ConnectionError("Fake connection error"),
            requests.Timeout("Fake connection timeout"),
        ],
    )
    def test_will_retry_errors(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            error,
            mock.Mock(content=json.dumps(fake_md)),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert len(mock_requests_session_request.mock_calls) == 2
        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)]
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                LOG_PATH,
                logging.INFO,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:"
                    f".*{error!s}.*"
                ),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Please wait 1 second.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[1/11\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    def test_will_retry_errors_on_fallback(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
    ):
        error = fake_http_error_for_code(400)
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            error,
            fake_http_error_for_code(429),
            mock.Mock(content=json.dumps(fake_md)),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert len(mock_requests_session_request.mock_calls) == 3
        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)]
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                LOG_PATH,
                logging.INFO,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:"
                    f".*{error!s}.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Failed to fetch metadata from IMDS: fake error",
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Falling back to IMDS api-version: 2019-06-01",
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                LOG_PATH,
                logging.INFO,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:"
                    f".*{error!s}.*"
                ),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Please wait 1 second.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[1/11\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(404),
            fake_http_error_for_code(410),
            fake_http_error_for_code(429),
            fake_http_error_for_code(500),
            requests.ConnectionError("Fake connection error"),
            requests.Timeout("Fake connection timeout"),
        ],
    )
    def test_retry_until_failure(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
    ):
        mock_requests_session_request.side_effect = [error] * (11)

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_metadata_with_api_fallback()

        assert exc_info.value.cause == error
        assert len(mock_requests_session_request.mock_calls) == (
            self.retries + 1
        )
        assert (
            mock_url_helper_time_sleep.mock_calls
            == [mock.call(1)] * self.retries
        )

        logs = [x for x in caplog.record_tuples if x[0] == LOG_PATH]
        assert logs == [
            (
                LOG_PATH,
                logging.INFO,
                StringMatch(
                    f"Polling IMDS failed attempt {i} with exception:"
                    f".*{error!s}.*"
                ),
            )
            for i in range(1, 12)
        ] + [
            (
                LOG_PATH,
                logging.WARNING,
                f"Failed to fetch metadata from IMDS: {error!s}",
            )
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(403),
            fake_http_error_for_code(501),
        ],
    )
    def test_will_not_retry_errors(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            error,
            mock.Mock(content=json.dumps(fake_md)),
        ]

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_metadata_with_api_fallback()

        assert exc_info.value.cause == error
        assert len(mock_requests_session_request.mock_calls) == 1
        assert mock_url_helper_time_sleep.mock_calls == []

        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/11\] open.*"),
            ),
            (
                LOG_PATH,
                logging.INFO,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:"
                    f".*{error!s}.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                f"Failed to fetch metadata from IMDS: {error!s}",
            ),
        ]

    def test_non_json_repsonse(
        self,
        caplog,
        mock_requests_session_request,
        wrapped_readurl,
    ):
        mock_requests_session_request.side_effect = [
            mock.Mock(content=b"bad data")
        ]

        with pytest.raises(ValueError):
            imds.fetch_metadata_with_api_fallback()

        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=mock.ANY,
                infinite=False,
                log_req_resp=True,
            ),
        ]

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == [
            (
                "Failed to parse metadata from IMDS: "
                "Expecting value: line 1 column 1 (char 0)"
            )
        ]


class TestFetchReprovisionData:
    url = (
        "http://169.254.169.254/metadata/"
        "reprovisiondata?api-version=2019-06-01"
    )
    headers = {"Metadata": "true"}
    timeout = 2

    def test_basic(
        self,
        caplog,
        mock_requests_session_request,
        wrapped_readurl,
    ):
        content = b"ovf content"
        mock_requests_session_request.side_effect = [
            mock.Mock(content=content),
        ]

        ovf = imds.fetch_reprovision_data()

        assert ovf == content
        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.url,
                timeout=self.timeout,
                headers=self.headers,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=False,
            ),
        ]

        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"Read from.*"),
            ),
            (
                LOG_PATH,
                logging.DEBUG,
                "Polled IMDS 1 time(s)",
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(404),
            fake_http_error_for_code(410),
        ],
    )
    @pytest.mark.parametrize("failures", [1, 5, 100, 1000])
    def test_will_retry_errors(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
        failures,
    ):
        content = b"ovf content"
        mock_requests_session_request.side_effect = [error] * failures + [
            mock.Mock(content=content),
        ]

        ovf = imds.fetch_reprovision_data()

        assert ovf == content
        assert len(mock_requests_session_request.mock_calls) == failures + 1
        assert (
            mock_url_helper_time_sleep.mock_calls == [mock.call(1)] * failures
        )

        wrapped_error = UrlError(
            error,
            code=error.response.status_code,
            headers=error.response.headers,
            url=self.url,
        )
        backoff_logs = [
            (
                LOG_PATH,
                logging.INFO,
                f"Polling IMDS failed attempt {i} with exception: "
                f"{wrapped_error!r}",
            )
            for i in range(1, failures + 1)
            if i == 1 or math.log2(i).is_integer()
        ]
        assert caplog.record_tuples == backoff_logs + [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"Read from.*"),
            ),
            (
                LOG_PATH,
                logging.DEBUG,
                f"Polled IMDS {failures+1} time(s)",
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(404),
            fake_http_error_for_code(410),
        ],
    )
    @pytest.mark.parametrize("failures", [1, 5, 100, 1000])
    @pytest.mark.parametrize(
        "terminal_error",
        [
            requests.ConnectionError("Fake connection error"),
            requests.Timeout("Fake connection timeout"),
        ],
    )
    def test_retry_until_failure(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
        failures,
        terminal_error,
    ):
        mock_requests_session_request.side_effect = [error] * failures + [
            terminal_error
        ]

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_reprovision_data()

        assert exc_info.value.cause == terminal_error
        assert len(mock_requests_session_request.mock_calls) == (failures + 1)
        assert (
            mock_url_helper_time_sleep.mock_calls == [mock.call(1)] * failures
        )

        wrapped_error = UrlError(
            error,
            code=error.response.status_code,
            headers=error.response.headers,
            url=self.url,
        )

        backoff_logs = [
            (
                LOG_PATH,
                logging.INFO,
                f"Polling IMDS failed attempt {i} with exception: "
                f"{wrapped_error!r}",
            )
            for i in range(1, failures + 1)
            if i == 1 or math.log2(i).is_integer()
        ]
        assert caplog.record_tuples == backoff_logs + [
            (
                LOG_PATH,
                logging.INFO,
                f"Polling IMDS failed attempt {failures+1} with exception: "
                f"{exc_info.value!r}",
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            fake_http_error_for_code(403),
            fake_http_error_for_code(501),
        ],
    )
    def test_will_not_retry_errors(
        self,
        caplog,
        mock_requests_session_request,
        mock_url_helper_time_sleep,
        error,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests_session_request.side_effect = [
            error,
            mock.Mock(content=json.dumps(fake_md)),
        ]

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_reprovision_data()

        assert exc_info.value.cause == error
        assert len(mock_requests_session_request.mock_calls) == 1
        assert mock_url_helper_time_sleep.mock_calls == []

        assert caplog.record_tuples == [
            (
                LOG_PATH,
                logging.INFO,
                "Polling IMDS failed attempt 1 with exception: "
                f"{exc_info.value!r}",
            ),
        ]
