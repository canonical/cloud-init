# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
import math
import re
from unittest import mock

import pytest
import requests
import responses

# TODO: Importing `errors` here is a hack to avoid a circular import.
# Without it, we have a azure->errors->identity->azure import loop, but
# long term we should restructure these modules to avoid the issue.
from cloudinit.sources.azure import errors as _errors  # noqa: F401
from cloudinit.sources.azure import imds
from cloudinit.url_helper import UrlError, readurl

LOG_PATH = "cloudinit.sources.azure.imds"
MOCK_PATH = "cloudinit.sources.azure.imds."


class StringMatch:
    def __init__(self, regex) -> None:
        self.regex = regex

    def __eq__(self, other) -> bool:
        return bool(re.match("^" + self.regex + "$", other))

    def __repr__(self) -> str:
        return repr(self.regex)


@pytest.fixture(autouse=True)
def caplog(caplog):
    # Ensure caplog is set to debug.
    caplog.set_level(logging.DEBUG)
    yield caplog


@pytest.fixture
def mock_requests():
    with responses.RequestsMock(
        assert_all_requests_are_fired=True
    ) as response:
        yield response


@pytest.fixture
def wrapped_readurl():
    with mock.patch.object(imds, "readurl", wraps=readurl) as m:
        yield m


@pytest.fixture
def mock_requests_session_request():
    with mock.patch("requests.Session.request", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_time_monotonic():
    with mock.patch.object(imds, "monotonic", autospec=True) as m:
        m.time_current = 0.0
        m.time_increment = 1.0

        def fake_time():
            nonlocal m
            current = m.time_current
            m.time_current += m.time_increment
            return current

        m.side_effect = fake_time
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


REQUESTS_CONNECTION_ERROR = requests.ConnectionError("Fake connection error")

REQUESTS_TIMEOUT_ERROR = requests.Timeout("Fake connection timeout")


def add_errors_to_mock_requests(mock_requests, errors, url):
    def callback_connection_error(request):
        raise REQUESTS_CONNECTION_ERROR

    def callback_timeout(request):
        raise REQUESTS_TIMEOUT_ERROR

    for error in errors:
        if isinstance(error, int):
            mock_requests.add(
                method=responses.GET,
                url=url,
                status=error,
            )
        elif error == REQUESTS_CONNECTION_ERROR:
            mock_requests.add_callback(
                method=responses.GET,
                url=url,
                callback=callback_connection_error,
            )
        elif error == REQUESTS_TIMEOUT_ERROR:
            mock_requests.add_callback(
                method=responses.GET,
                url=url,
                callback=callback_timeout,
            )
        else:
            assert False


def regex_for_http_error(error):
    if isinstance(error, int):
        return f".*{error!s}.*"

    # Returns 'Fake connection error' or 'Fake connection timeout'
    return f".*{error!s}.*"


class TestHeaders:
    default_url = (
        "http://169.254.169.254/metadata/instance?"
        "api-version=2021-08-01&extended=true"
    )

    def test_headers_cb(self):
        headers = imds.headers_cb(self.default_url)
        assert list(headers.keys()) == ["Metadata", "x-ms-client-request-id"]
        assert headers.get("Metadata") == "true"
        uuid = headers.get("x-ms-client-request-id")
        match = re.search(
            "^[a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-"
            "[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}$",
            uuid,
        )
        assert match


class TestFetchMetadataWithApiFallback:
    default_url = (
        "http://169.254.169.254/metadata/instance?"
        "api-version=2021-08-01&extended=true"
    )
    fallback_url = (
        "http://169.254.169.254/metadata/instance?api-version=2019-06-01"
    )

    # Early versions of responses do not appreciate the parameters...
    base_url = "http://169.254.169.254/metadata/instance"
    timeout = 30

    @pytest.mark.parametrize("retry_deadline", [0.0, 1.0, 60.0])
    def test_basic(
        self,
        caplog,
        retry_deadline,
        wrapped_readurl,
        mock_requests,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            json=fake_md,
            status=200,
        )

        md = imds.fetch_metadata_with_api_fallback(
            retry_deadline=retry_deadline
        )

        assert md == fake_md
        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=True,
            )
        ]
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    @pytest.mark.parametrize("retry_deadline", [0.0, 1.0, 60.0])
    def test_basic_fallback(
        self, caplog, retry_deadline, wrapped_readurl, mock_requests
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            status=400,
        )
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            json=fake_md,
            status=200,
        )

        md = imds.fetch_metadata_with_api_fallback(
            retry_deadline=retry_deadline
        )

        assert md == fake_md
        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=True,
            ),
            mock.call(
                self.fallback_url,
                timeout=self.timeout,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
                log_req_resp=True,
            ),
        ]

        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(
                    r"\[0/infinite\] open.*Metadata.*true"
                    ".*x-ms-client-request-id.*[a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-"
                    "[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch("Polling IMDS failed attempt 1 with.*400.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Failed to fetch metadata from IMDS:.*400 Client Error.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Falling back to IMDS api-version: 2019-06-01",
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                f"Read from {self.fallback_url} (200, 20b) after 1 attempts",
            ),
        ]

    @pytest.mark.parametrize(
        "error",
        [
            404,
            410,
            429,
            500,
            REQUESTS_CONNECTION_ERROR,
            REQUESTS_TIMEOUT_ERROR,
        ],
    )
    @pytest.mark.parametrize("error_count,retry_deadline", [(1, 2.0)])
    def test_will_retry_errors(
        self,
        caplog,
        retry_deadline,
        mock_requests,
        mock_url_helper_time_sleep,
        error,
        error_count,
    ):
        fake_md = {"foo": {"bar": []}}
        add_errors_to_mock_requests(
            mock_requests, [error] * error_count, self.base_url
        )
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            json=fake_md,
            status=200,
        )

        md = imds.fetch_metadata_with_api_fallback(
            retry_deadline=retry_deadline
        )

        assert md == fake_md
        assert (
            mock_url_helper_time_sleep.mock_calls
            == [mock.call(1)] * error_count
        )

        error_regex = regex_for_http_error(error)
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception: "
                    f"{error_regex}"
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
                StringMatch(r"\[1/infinite\] open.*"),
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch("Read from.*"),
            ),
        ]

    @pytest.mark.parametrize("retry_deadline", [3.0, 30.0])
    def test_will_retry_errors_on_fallback(
        self,
        caplog,
        retry_deadline,
        mock_requests,
        mock_url_helper_time_sleep,
    ):
        fake_md = {"foo": {"bar": []}}
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            status=400,
        )
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            status=429,
        )
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            json=fake_md,
            status=200,
        )

        md = imds.fetch_metadata_with_api_fallback(
            retry_deadline=retry_deadline
        )

        assert md == fake_md
        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)]
        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:.*400.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Failed to fetch metadata from IMDS:.*400 Client Error.*"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                "Falling back to IMDS api-version: 2019-06-01",
            ),
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:.*429.*"
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
                StringMatch(r"\[1/infinite\] open.*"),
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
            404,
            410,
            429,
            500,
            REQUESTS_CONNECTION_ERROR,
            REQUESTS_TIMEOUT_ERROR,
        ],
    )
    @pytest.mark.parametrize(
        "error_count,retry_deadline", [(1, 0.0), (2, 1.0), (301, 300.0)]
    )
    @pytest.mark.parametrize("max_connection_errors", [None, 1, 11])
    def test_retry_until_failure(
        self,
        error,
        error_count,
        max_connection_errors,
        retry_deadline,
        caplog,
        mock_requests,
        mock_url_helper_time_sleep,
    ):
        add_errors_to_mock_requests(
            mock_requests, [error] * error_count, self.base_url
        )

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_metadata_with_api_fallback(
                max_connection_errors=max_connection_errors,
                retry_deadline=retry_deadline,
            )

        error_regex = regex_for_http_error(error)
        assert re.search(error_regex, str(exc_info.value.cause))

        max_attempts = (
            min(max_connection_errors, int(retry_deadline) + 1)
            if isinstance(error, requests.ConnectionError)
            and isinstance(max_connection_errors, int)
            else error_count
        )

        if max_attempts < error_count:
            mock_requests.assert_all_requests_are_fired = False

        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)] * (
            max_attempts - 1
        )

        logs = [x for x in caplog.record_tuples if x[0] == LOG_PATH]
        assert logs == [
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    f"Polling IMDS failed attempt {i} with exception:"
                    f"{error_regex}"
                ),
            )
            for i in range(1, max_attempts + 1)
        ] + [
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    f"Failed to fetch metadata from IMDS: {error_regex}",
                ),
            )
        ]

    @pytest.mark.parametrize(
        "error",
        [
            403,
            501,
        ],
    )
    @pytest.mark.parametrize("retry_deadline", [0.0, 1.0, 60.0])
    def test_will_not_retry_errors(
        self,
        error,
        retry_deadline,
        caplog,
        mock_requests,
        mock_url_helper_time_sleep,
    ):
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            status=error,
        )

        with pytest.raises(UrlError) as exc_info:
            imds.fetch_metadata_with_api_fallback(
                retry_deadline=retry_deadline
            )

        error_regex = regex_for_http_error(error)
        assert re.search(error_regex, str(exc_info.value.cause))
        assert mock_url_helper_time_sleep.mock_calls == []

        assert caplog.record_tuples == [
            (
                "cloudinit.url_helper",
                logging.DEBUG,
                StringMatch(r"\[0/infinite\] open.*"),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    "Polling IMDS failed attempt 1 with exception:"
                    f".*{error_regex}"
                ),
            ),
            (
                LOG_PATH,
                logging.WARNING,
                StringMatch(
                    f"Failed to fetch metadata from IMDS: {error_regex!s}"
                ),
            ),
        ]

    @pytest.mark.parametrize("body", ["", "invalid", "<tag></tag>"])
    @pytest.mark.parametrize("retry_deadline", [0.0, 1.0, 60.0])
    def test_non_json_repsonse(
        self,
        body,
        retry_deadline,
        caplog,
        mock_requests,
        wrapped_readurl,
    ):
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            body=body,
        )

        with pytest.raises(ValueError):
            imds.fetch_metadata_with_api_fallback(
                retry_deadline=retry_deadline
            )

        assert wrapped_readurl.mock_calls == [
            mock.call(
                self.default_url,
                timeout=self.timeout,
                headers_cb=imds.headers_cb,
                exception_cb=mock.ANY,
                infinite=True,
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

    def test_logs_all_errors(
        self,
        caplog,
        mock_requests,
        mock_url_helper_time_sleep,
    ):
        fake_md = {"foo": {"bar": []}}

        errors = (
            [404] * 10
            + [410] * 10
            + [429] * 10
            + [500] * 10
            + [REQUESTS_CONNECTION_ERROR] * 10
            + [REQUESTS_TIMEOUT_ERROR] * 10
        )

        add_errors_to_mock_requests(mock_requests, errors, self.base_url)
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            json=fake_md,
        )

        md = imds.fetch_metadata_with_api_fallback(retry_deadline=300)

        assert md == fake_md
        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)] * (
            len(errors)
        )

        expected_logs = [
            StringMatch(
                f"Polling IMDS failed attempt {i} with exception:"
                f"{regex_for_http_error(error)}"
            )
            for i, error in enumerate(errors, start=1)
        ]
        logs = [t[2] for t in caplog.record_tuples if "Polling IMDS" in t[2]]
        assert logs == expected_logs


class TestFetchReprovisionData:
    url = (
        "http://169.254.169.254/metadata/"
        "reprovisiondata?api-version=2019-06-01"
    )
    timeout = 30

    # Early versions of responses do not appreciate the parameters...
    base_url = "http://169.254.169.254/metadata/reprovisiondata"

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
                headers_cb=imds.headers_cb,
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
            fake_http_error_for_code(429),
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
                logging.WARNING,
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
            fake_http_error_for_code(429),
        ],
    )
    @pytest.mark.parametrize("failures", [1, 5, 100, 1000])
    @pytest.mark.parametrize(
        "terminal_error",
        [
            requests.ConnectionError("Fake connection error"),
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
                logging.WARNING,
                f"Polling IMDS failed attempt {i} with exception: "
                f"{wrapped_error!r}",
            )
            for i in range(1, failures + 1)
            if i == 1 or math.log2(i).is_integer()
        ]
        assert caplog.record_tuples == backoff_logs + [
            (
                LOG_PATH,
                logging.WARNING,
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
                logging.WARNING,
                "Polling IMDS failed attempt 1 with exception: "
                f"{exc_info.value!r}",
            ),
        ]

    def test_logs_unique_errors(
        self,
        caplog,
        mock_requests,
        mock_url_helper_time_sleep,
    ):
        content = b"ovf content"

        errors = (
            [404] * 10
            + [410] * 10
            + [429] * 10
            + [404] * 10
            + [410] * 10
            + [429] * 10
        )

        add_errors_to_mock_requests(mock_requests, errors, self.base_url)
        mock_requests.add(
            method=responses.GET,
            url=self.base_url,
            body=content,
        )

        ovf = imds.fetch_reprovision_data()

        assert ovf == content
        assert mock_url_helper_time_sleep.mock_calls == [mock.call(1)] * (
            len(errors)
        )

        backoff_logs = [
            StringMatch(
                f"Polling IMDS failed attempt {i} with exception:"
                f"{regex_for_http_error(error)}"
            )
            for i, error in enumerate(errors, start=1)
            if i == 1 or math.log2(i).is_integer() or (i - 1) % 10 == 0
        ]
        logs = [t[2] for t in caplog.record_tuples if "Polling IMDS" in t[2]]
        assert logs == backoff_logs
