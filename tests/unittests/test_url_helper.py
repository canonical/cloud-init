# This file is part of cloud-init. See LICENSE file for license information.
# pylint: disable=attribute-defined-outside-init

import logging
import re
from functools import partial
from threading import Event
from time import process_time
from unittest.mock import ANY, call

import pytest
import requests
import responses

from cloudinit import util, version
from cloudinit.url_helper import (
    REDACTED,
    UrlError,
    UrlResponse,
    dual_stack,
    oauth_headers,
    read_file_or_url,
    readurl,
    wait_for_url,
)
from tests.unittests.helpers import CiTestCase, mock, skipIf

try:
    import oauthlib

    assert oauthlib  # avoid pyflakes error F401: import unused
    _missing_oauthlib_dep = False
except ImportError:
    _missing_oauthlib_dep = True


M_PATH = "cloudinit.url_helper."


class TestOAuthHeaders(CiTestCase):
    def test_oauth_headers_raises_not_implemented_when_oathlib_missing(self):
        """oauth_headers raises a NotImplemented error when oauth absent."""
        with mock.patch.dict("sys.modules", {"oauthlib": None}):
            with self.assertRaises(NotImplementedError) as context_manager:
                oauth_headers(1, 2, 3, 4, 5)
        self.assertEqual(
            "oauth support is not available", str(context_manager.exception)
        )

    @skipIf(_missing_oauthlib_dep, "No python-oauthlib dependency")
    @mock.patch("oauthlib.oauth1.Client")
    def test_oauth_headers_calls_oathlibclient_when_available(self, m_client):
        """oauth_headers calls oaut1.hClient.sign with the provided url."""

        class fakeclient:
            def sign(self, url):
                # The first and 3rd item of the client.sign tuple are ignored
                return ("junk", url, "junk2")

        m_client.return_value = fakeclient()

        return_value = oauth_headers(
            "url",
            "consumer_key",
            "token_key",
            "token_secret",
            "consumer_secret",
        )
        self.assertEqual("url", return_value)


class TestReadFileOrUrl(CiTestCase):

    with_logs = True

    def test_read_file_or_url_str_from_file(self):
        """Test that str(result.contents) on file is text version of contents.
        It should not be "b'data'", but just "'data'" """
        tmpf = self.tmp_path("myfile1")
        data = b"This is my file content\n"
        util.write_file(tmpf, data, omode="wb")
        result = read_file_or_url("file://%s" % tmpf)
        self.assertEqual(result.contents, data)
        self.assertEqual(str(result), data.decode("utf-8"))

    @responses.activate
    def test_read_file_or_url_str_from_url(self):
        """Test that str(result.contents) on url is text version of contents.
        It should not be "b'data'", but just "'data'" """
        url = "http://hostname/path"
        data = b"This is my url content\n"
        responses.add(responses.GET, url, data)
        result = read_file_or_url(url)
        self.assertEqual(result.contents, data)
        self.assertEqual(str(result), data.decode("utf-8"))

    @responses.activate
    def test_read_file_or_url_str_from_url_streamed(self):
        """Test that str(result.contents) on url is text version of contents.
        It should not be "b'data'", but just "'data'" """
        url = "http://hostname/path"
        data = b"This is my url content\n"
        responses.add(responses.GET, url, data)
        result = read_file_or_url(url, stream=True)
        assert isinstance(result, UrlResponse)
        self.assertEqual(result.contents, data)
        self.assertEqual(str(result), data.decode("utf-8"))

    @responses.activate
    def test_read_file_or_url_str_from_url_redacting_headers_from_logs(self):
        """Headers are redacted from logs but unredacted in requests."""
        url = "http://hostname/path"
        headers = {"sensitive": "sekret", "server": "blah"}

        def _request_callback(request):
            for k in headers.keys():
                self.assertEqual(headers[k], request.headers[k])
            return (200, request.headers, "does_not_matter")

        responses.add_callback(responses.GET, url, callback=_request_callback)

        read_file_or_url(url, headers=headers, headers_redact=["sensitive"])
        logs = self.logs.getvalue()
        self.assertIn(REDACTED, logs)
        self.assertNotIn("sekret", logs)

    @responses.activate
    def test_read_file_or_url_str_from_url_redacts_noheaders(self):
        """When no headers_redact, header values are in logs and requests."""
        url = "http://hostname/path"
        headers = {"sensitive": "sekret", "server": "blah"}

        def _request_callback(request):
            for k in headers.keys():
                self.assertEqual(headers[k], request.headers[k])
            return (200, request.headers, "does_not_matter")

        responses.add_callback(responses.GET, url, callback=_request_callback)

        read_file_or_url(url, headers=headers)
        logs = self.logs.getvalue()
        self.assertNotIn(REDACTED, logs)
        self.assertIn("sekret", logs)

    def test_wb_read_url_defaults_honored_by_read_file_or_url_callers(self):
        """Readurl param defaults used when unspecified by read_file_or_url

        Param defaults tested are as follows:
            retries: 0, additional headers None beyond default, method: GET,
            data: None, check_status: True and allow_redirects: True
        """
        url = "http://hostname/path"

        m_response = mock.MagicMock()

        class FakeSessionRaisesHttpError(requests.Session):
            @classmethod
            def request(cls, **kwargs):
                raise requests.exceptions.HTTPError("broke")

        class FakeSession(requests.Session):
            @classmethod
            def request(cls, **kwargs):
                self.assertEqual(
                    {
                        "url": url,
                        "allow_redirects": True,
                        "method": "GET",
                        "headers": {
                            "User-Agent": "Cloud-Init/%s"
                            % (version.version_string())
                        },
                        "stream": False,
                    },
                    kwargs,
                )
                return m_response

        with mock.patch(M_PATH + "requests.Session") as m_session:
            m_session.side_effect = [
                FakeSessionRaisesHttpError(),
                FakeSession(),
            ]
            # assert no retries and check_status == True
            with self.assertRaises(UrlError) as context_manager:
                response = read_file_or_url(url)
            self.assertEqual("broke", str(context_manager.exception))
            # assert default headers, method, url and allow_redirects True
            # Success on 2nd call with FakeSession
            response = read_file_or_url(url)
        self.assertEqual(m_response, response._response)


class TestReadFileOrUrlParameters:
    @mock.patch(M_PATH + "readurl")
    @pytest.mark.parametrize(
        "timeout", [1, 1.2, "1", (1, None), (1, 1), (None, None)]
    )
    def test_read_file_or_url_passes_params_to_readurl(
        self, m_readurl, timeout
    ):
        """read_file_or_url passes all params through to readurl."""
        url = "http://hostname/path"
        response = "This is my url content\n"
        m_readurl.return_value = response
        params = {
            "url": url,
            "timeout": timeout,
            "retries": 2,
            "headers": {"somehdr": "val"},
            "data": "data",
            "sec_between": 1,
            "ssl_details": {"cert_file": "/path/cert.pem"},
            "headers_cb": "headers_cb",
            "exception_cb": "exception_cb",
            "stream": True,
        }

        assert response == read_file_or_url(**params)
        params.pop("url")  # url is passed in as a positional arg
        assert m_readurl.call_args_list == [mock.call(url, **params)]

    @pytest.mark.parametrize(
        "readurl_timeout,request_timeout",
        [
            (-1, 0),
            ("-1", 0),
            (None, None),
            (1, 1.0),
            (1.2, 1.2),
            ("1", 1.0),
            ((1, None), (1, None)),
            ((1, 1), (1, 1)),
            ((None, None), (None, None)),
        ],
    )
    def test_readurl_timeout(self, readurl_timeout, request_timeout):
        url = "http://hostname/path"
        m_response = mock.MagicMock()

        class FakeSession(requests.Session):
            @classmethod
            def request(cls, **kwargs):
                expected_kwargs = {
                    "url": url,
                    "allow_redirects": True,
                    "method": "GET",
                    "headers": {
                        "User-Agent": "Cloud-Init/%s"
                        % (version.version_string())
                    },
                    "timeout": request_timeout,
                    "stream": False,
                }
                if request_timeout is None:
                    expected_kwargs.pop("timeout")

                assert kwargs == expected_kwargs
                return m_response

        with mock.patch(
            M_PATH + "requests.Session", side_effect=[FakeSession()]
        ):
            response = read_file_or_url(url, timeout=readurl_timeout)

        assert response._response == m_response


def assert_time(func, max_time=1):
    """Assert function time is bounded by a max (default=1s)

    The following async tests should canceled in under 1ms and have stagger
    delay and max_
    It is possible that this could yield a false positive, but this should
    basically never happen (esp under normal system load).
    """
    start = process_time()
    try:
        out = func()
    finally:
        diff = process_time() - start
        assert diff < max_time
    return out


class TestReadUrl:
    @pytest.mark.parametrize("headers", [{}, {"Metadata": "true"}])
    def test_headers(self, headers):
        url = "http://hostname/path"
        m_response = mock.MagicMock()

        expected_headers = headers.copy()
        expected_headers["User-Agent"] = "Cloud-Init/%s" % (
            version.version_string()
        )

        class FakeSession(requests.Session):
            @classmethod
            def request(cls, **kwargs):
                expected_kwargs = {
                    "url": url,
                    "allow_redirects": True,
                    "method": "GET",
                    "headers": expected_headers,
                    "stream": False,
                }

                assert kwargs == expected_kwargs
                return m_response

        with mock.patch(
            M_PATH + "requests.Session", side_effect=[FakeSession()]
        ):
            response = readurl(url, headers=headers)

        assert response._response == m_response

    @pytest.mark.parametrize("headers", [{}, {"Metadata": "true"}])
    def test_headers_cb(self, headers):
        url = "http://hostname/path"
        m_response = mock.MagicMock()

        expected_headers = headers.copy()
        expected_headers["User-Agent"] = "Cloud-Init/%s" % (
            version.version_string()
        )
        headers_cb = lambda _: headers

        class FakeSession(requests.Session):
            @classmethod
            def request(cls, **kwargs):
                expected_kwargs = {
                    "url": url,
                    "allow_redirects": True,
                    "method": "GET",
                    "headers": expected_headers,
                    "stream": False,
                }

                assert kwargs == expected_kwargs
                return m_response

        with mock.patch(
            M_PATH + "requests.Session", side_effect=[FakeSession()]
        ):
            response = readurl(url, headers_cb=headers_cb)

        assert response._response == m_response


event = Event()


class TestDualStack:
    """Async testing suggestions welcome - these all rely on time-bounded
    assertions (via threading.Event) to prove ordering
    """

    @pytest.mark.parametrize(
        ["func", "addresses", "stagger_delay", "timeout", "expected_val"],
        [
            # Assert order based on timeout
            (lambda x, _: x, ("one", "two"), 1, 1, "one"),
            # Assert timeout results in (None, None)
            (lambda _a, _b: event.wait(1), ("one", "two"), 1, 0, None),
            (
                lambda a, _b: 1 / 0 if a == "one" else a,
                ("one", "two"),
                0,
                1,
                "two",
            ),
            # Assert that exception in func is only raised
            # if neither thread gets a valid result
            (
                lambda a, _b: 1 / 0 if a == "two" else a,
                ("one", "two"),
                0,
                1,
                "one",
            ),
            # simulate a slow response to verify correct order
            (
                lambda x, _: event.wait(1) if x != "two" else x,
                ("one", "two"),
                0,
                1,
                "two",
            ),
            # simulate a slow response to verify correct order
            (
                lambda x, _: event.wait(1) if x != "tri" else x,
                ("one", "two", "tri"),
                0,
                1,
                "tri",
            ),
        ],
    )
    def test_dual_stack(
        self,
        func,
        addresses,
        stagger_delay,
        timeout,
        expected_val,
    ):
        """Assert various failure modes behave as expected"""
        event.clear()

        gen = partial(
            dual_stack,
            func,
            addresses,
            stagger_delay=stagger_delay,
            timeout=timeout,
        )
        _, result = assert_time(gen)
        assert expected_val == result

        event.set()

    @pytest.mark.parametrize(
        [
            "func",
            "addresses",
            "stagger_delay",
            "timeout",
            "message",
            "expected_exc",
        ],
        [
            (
                lambda _a, _b: 1 / 0,
                ("¯\\_(ツ)_/¯", "(╯°□°）╯︵ ┻━┻"),
                0,
                1,
                "division by zero",
                ZeroDivisionError,
            ),
            (
                lambda _a, _b: 1 / 0,
                ("it", "really", "doesn't"),
                0,
                1,
                "division by zero",
                ZeroDivisionError,
            ),
            (
                lambda _a, _b: [][0],  # pylint: disable=E0643
                ("matter", "these"),
                0,
                1,
                "list index out of range",
                IndexError,
            ),
            (
                lambda _a, _b: (_ for _ in ()).throw(
                    Exception("soapstone is not effective soap")
                ),
                ("are", "ignored"),
                0,
                1,
                "soapstone is not effective soap",
                Exception,
            ),
        ],
    )
    def test_dual_stack_exceptions(
        self,
        func,
        addresses,
        stagger_delay,
        timeout,
        message,
        expected_exc,
        caplog,
    ):
        # Context:
        #
        # currently if all threads experience exception
        # dual_stack() logs an error containing all exceptions
        # but only raises the last exception to occur
        # Verify "best effort behavior"
        # dual_stack will temporarily ignore an exception in any of the
        # request threads in hopes that a later thread will succeed
        # this behavior is intended to allow a requests.ConnectionError
        # exception from on endpoint to occur without preventing another
        # thread from succeeding
        event.clear()

        # Note: python3.6 repr(Exception("test")) produces different output
        # than later versions, so we cannot match exact message without
        # some ugly manual exception repr() function, which I'd rather not do
        # in dual_stack(), so we recreate expected messages manually here
        # in a version-independant way for testing, the extra comma on old
        # versions won't hurt anything
        exc_list = str([expected_exc(message) for _ in addresses])
        expected_msg = f"Exception(s) {exc_list} during request"
        gen = partial(
            dual_stack,
            func,
            addresses,
            stagger_delay=stagger_delay,
            timeout=timeout,
        )
        with pytest.raises(expected_exc):
            gen()  # 1
        with caplog.at_level(logging.DEBUG):
            try:
                gen()  # 2
            except expected_exc:
                pass
            finally:
                assert 2 == len(caplog.records)
                assert 2 == caplog.text.count(expected_msg)
        event.set()

    def test_dual_stack_staggered(self):
        """Assert expected call intervals occur"""
        stagger = 0.1
        with mock.patch(M_PATH + "_run_func_with_delay") as delay_func:

            def identity_of_first_arg(x, _):
                return x

            dual_stack(
                identity_of_first_arg,
                ["you", "and", "me", "and", "dog"],
                stagger_delay=stagger,
                timeout=1,
            )

            # ensure that stagger delay for each call is made with args:
            # [ 0 * N, 1 * N, 2 * N, 3 * N, 4 * N, 5 * N] where N = stagger
            # it appears that without an explicit wait/join we can't assert
            # number of calls
            calls = [
                call(
                    func=identity_of_first_arg,
                    addr="you",
                    timeout=1,
                    event=ANY,
                    delay=stagger * 0,
                ),
                call(
                    func=identity_of_first_arg,
                    addr="and",
                    timeout=1,
                    event=ANY,
                    delay=stagger * 1,
                ),
                call(
                    func=identity_of_first_arg,
                    addr="me",
                    timeout=1,
                    event=ANY,
                    delay=stagger * 2,
                ),
                call(
                    func=identity_of_first_arg,
                    addr="and",
                    timeout=1,
                    event=ANY,
                    delay=stagger * 3,
                ),
                call(
                    func=identity_of_first_arg,
                    addr="dog",
                    timeout=1,
                    event=ANY,
                    delay=stagger * 4,
                ),
            ]
            num_calls = 0
            for call_instance in calls:
                if call_instance in delay_func.call_args_list:
                    num_calls += 1

            # we can't know the order of the submitted functions' execution
            # we can't know how many of the submitted functions get called
            # in advance
            #
            # we _do_ know what the possible arg combinations are
            # we _do_ know from the mocked function how many got called
            # assert that all calls that occurred had known valid arguments
            # by checking for the correct number of matches
            assert num_calls == len(delay_func.call_args_list)


ADDR1 = "https://addr1/"
SLEEP1 = "https://sleep1/"
SLEEP2 = "https://sleep2/"


class TestUrlHelper:
    success = "SUCCESS"
    fail = "FAIL"
    event = Event()

    @pytest.fixture
    def retry_mocks(self, mocker):
        self.mock_time_value = 0
        m_readurl = mocker.patch(
            f"{M_PATH}readurl", side_effect=self.readurl_side_effect
        )
        m_sleep = mocker.patch(
            f"{M_PATH}time.sleep", side_effect=self.sleep_side_effect
        )
        mocker.patch(
            f"{M_PATH}time.monotonic", side_effect=self.time_side_effect
        )

        yield m_readurl, m_sleep

        self.mock_time_value = 0

    @classmethod
    def response_wait(cls, _request):
        cls.event.wait(0.1)
        return (500, {"request-id": "1"}, cls.fail)

    @classmethod
    def response_nowait(cls, _request):
        return (200, {"request-id": "0"}, cls.success)

    @pytest.mark.parametrize(
        ["addresses", "expected_address_index", "response"],
        [
            # Use timeout to test ordering happens as expected
            ((ADDR1, SLEEP1), 0, "SUCCESS"),
            ((SLEEP1, ADDR1), 1, "SUCCESS"),
            ((SLEEP1, SLEEP2, ADDR1), 2, "SUCCESS"),
            ((ADDR1, SLEEP1, SLEEP2), 0, "SUCCESS"),
        ],
    )
    @responses.activate
    def test_order(self, addresses, expected_address_index, response):
        """Check that the first response gets returned. Simulate a
        non-responding endpoint with a response that has a one second wait.

        If this test proves flaky, increase wait time. Since it is async,
        increasing wait time for the non-responding endpoint should not
        increase total test time, assuming async_delay=0 is used and at least
        one non-waiting endpoint is registered with responses.
        Subsequent tests will continue execution after the first response is
        received.
        """
        self.event.clear()
        for address in set(addresses):
            responses.add_callback(
                responses.GET,
                address,
                callback=(
                    self.response_wait
                    if "sleep" in address
                    else self.response_nowait
                ),
                content_type="application/json",
            )

        # Use async_delay=0.0 to avoid adding unnecessary time to tests
        # In practice a value such as 0.150 is used
        url, response_contents = wait_for_url(
            urls=addresses,
            max_wait=1,
            timeout=1,
            connect_synchronously=False,
            async_delay=0.0,
        )
        self.event.set()

        # Test for timeout (no responding endpoint)
        assert addresses[expected_address_index] == url
        assert response.encode() == response_contents

    @responses.activate
    def test_timeout(self, caplog):
        """If no endpoint responds in time, expect no response"""

        self.event.clear()
        addresses = [SLEEP1, SLEEP2]
        for address in set(addresses):
            responses.add_callback(
                responses.GET,
                address,
                callback=(
                    requests.ConnectTimeout
                    if "sleep" in address
                    else self.response_nowait
                ),
                content_type="application/json",
            )

        # Use async_delay=0.0 to avoid adding unnecessary time to tests
        url, response_contents = wait_for_url(
            urls=addresses,
            max_wait=1,
            timeout=1,
            connect_synchronously=False,
            async_delay=0,
        )
        self.event.set()
        assert not url
        assert not response_contents
        assert re.search(
            r"open 'https:\/\/sleep1\/'.*Timed out", caplog.text, re.DOTALL
        )

    def test_explicit_arguments(self, retry_mocks):
        """Ensure that explicit arguments are respected"""
        m_readurl, m_sleep = retry_mocks
        wait_for_url(
            urls=["http://localhost/"],
            max_wait=23,
            timeout=5,
            sleep_time=3,
        )

        assert len(m_readurl.call_args_list) == 3
        assert len(m_sleep.call_args_list) == 2

        for readurl_call in m_readurl.call_args_list:
            assert readurl_call[1]["timeout"] == 5
        for sleep_call in m_sleep.call_args_list:
            assert sleep_call[0][0] == 3

        # Call 1 starts 0
        # Call 2 starts at 8-ish after 5 second timeout and 3 second sleep
        # Call 3 starts at 16-ish for same reasons
        # The 5 second timeout puts us at 21-ish and now we break
        # because 21-ish + the sleep time puts us over max wait of 23
        assert pytest.approx(self.mock_time_value) == 21

    def test_shortened_timeout(self, retry_mocks):
        """Test that we shorten the last timeout to align with max_wait"""
        m_readurl, _m_sleep = retry_mocks
        wait_for_url(
            urls=["http://localhost/"], max_wait=10, timeout=9, sleep_time=0
        )

        assert len(m_readurl.call_args_list) == 2
        assert m_readurl.call_args_list[-1][1]["timeout"] == pytest.approx(1)

    def test_default_sleep_time(self, retry_mocks):
        """Test default sleep behavior when not specified"""
        _m_readurl, m_sleep = retry_mocks
        wait_for_url(
            urls=["http://localhost/"],
            max_wait=50,
            timeout=1,
        )

        expected_sleep_times = [1] * 5 + [2] * 5 + [3] * 5
        actual_sleep_times = [
            m_sleep.call_args_list[i][0][0]
            for i in range(len(m_sleep.call_args_list))
        ]
        assert actual_sleep_times == expected_sleep_times

    # These side effect methods are a way of having a somewhat predictable
    # output for time.monotonic(). Otherwise, we have to track too many calls
    # to time.monotonic() and unrelated changes to code being called could
    # cause these tests to fail.
    # 0.0000001 is added to simulate additional execution time but keep it
    # small enough for pytest.approx() to work
    def sleep_side_effect(self, sleep_time):
        self.mock_time_value += sleep_time + 0.0000001

    def time_side_effect(self):
        return self.mock_time_value

    def readurl_side_effect(self, *args, **kwargs):
        if "timeout" in kwargs:
            self.mock_time_value += kwargs["timeout"] + 0.0000001
        raise UrlError("test")
