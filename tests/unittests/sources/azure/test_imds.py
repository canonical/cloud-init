# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import math
from unittest import mock

import pytest
import requests

from cloudinit.sources.azure import imds
from cloudinit.url_helper import UrlError

MOCKPATH = "cloudinit.sources.azure.imds."


@pytest.fixture
def mock_readurl():
    with mock.patch(MOCKPATH + "readurl", autospec=True) as m:
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
        mock_readurl,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_readurl.side_effect = [
            mock.Mock(contents=json.dumps(fake_md).encode()),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert mock_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=imds._readurl_exception_callback,
                infinite=False,
                log_req_resp=True,
            ),
        ]

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == []

    def test_basic_fallback(
        self,
        caplog,
        mock_readurl,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_readurl.side_effect = [
            UrlError("No IMDS version", code=400),
            mock.Mock(contents=json.dumps(fake_md).encode()),
        ]

        md = imds.fetch_metadata_with_api_fallback()

        assert md == fake_md
        assert mock_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=imds._readurl_exception_callback,
                infinite=False,
                log_req_resp=True,
            ),
            mock.call(
                self.fallback_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=imds._readurl_exception_callback,
                infinite=False,
                log_req_resp=True,
            ),
        ]

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == [
            "Failed to fetch metadata from IMDS: No IMDS version",
            "Falling back to IMDS api-version: 2019-06-01",
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

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == []

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

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == [
            "Failed to fetch metadata from IMDS: fake error",
            "Falling back to IMDS api-version: 2019-06-01",
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

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == [f"Failed to fetch metadata from IMDS: {error!s}"]

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

        warnings = [
            x.message for x in caplog.records if x.levelno == logging.WARNING
        ]
        assert warnings == [f"Failed to fetch metadata from IMDS: {error!s}"]

    def test_non_json_repsonse(
        self,
        caplog,
        mock_readurl,
    ):
        mock_readurl.side_effect = [
            mock.Mock(contents=b"bad data"),
        ]

        with pytest.raises(ValueError):
            imds.fetch_metadata_with_api_fallback()

        assert mock_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers=self.headers,
                retries=self.retries,
                exception_cb=imds._readurl_exception_callback,
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
        mock_readurl,
    ):
        content = b"ovf content"
        mock_readurl.side_effect = [
            mock.Mock(contents=content),
        ]

        ovf = imds.fetch_reprovision_data()

        assert ovf == content
        assert mock_readurl.mock_calls == [
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
                "cloudinit.sources.azure.imds",
                logging.DEBUG,
                "Polled IMDS 1 time(s)",
            )
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
                "cloudinit.sources.azure.imds",
                logging.INFO,
                "Polling IMDS failed with exception: "
                f"{wrapped_error!r} count: {i}",
            )
            for i in range(1, failures + 1)
            if i == 1 or math.log2(i).is_integer()
        ]
        assert caplog.record_tuples == backoff_logs + [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                mock.ANY,
            ),
            (
                "cloudinit.sources.azure.imds",
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
                "cloudinit.sources.azure.imds",
                logging.INFO,
                "Polling IMDS failed with exception: "
                f"{wrapped_error!r} count: {i}",
            )
            for i in range(1, failures + 1)
            if i == 1 or math.log2(i).is_integer()
        ]
        assert caplog.record_tuples == backoff_logs + [
            (
                "cloudinit.sources.azure.imds",
                logging.INFO,
                "Polling IMDS failed with exception: "
                f"{exc_info.value!r} count: {failures+1}",
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
                "cloudinit.sources.azure.imds",
                logging.INFO,
                "Polling IMDS failed with exception: "
                f"{exc_info.value!r} count: 1",
            ),
        ]
