# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from email.utils import parsedate
from errno import ENOENT
from functools import partial
from http.client import NOT_FOUND
from itertools import count
from typing import Any, Callable, Iterator, List, Optional, Tuple, Union
from urllib.parse import quote, urlparse, urlunparse

import requests
from requests import exceptions

from cloudinit import version

LOG = logging.getLogger(__name__)

REDACTED = "REDACTED"


def _cleanurl(url):
    parsed_url = list(urlparse(url, scheme="http"))
    if not parsed_url[1] and parsed_url[2]:
        # Swap these since this seems to be a common
        # occurrence when given urls like 'www.google.com'
        parsed_url[1] = parsed_url[2]
        parsed_url[2] = ""
    return urlunparse(parsed_url)


def combine_url(base, *add_ons):
    def combine_single(url, add_on):
        url_parsed = list(urlparse(url))
        path = url_parsed[2]
        if path and not path.endswith("/"):
            path += "/"
        path += quote(str(add_on), safe="/:")
        url_parsed[2] = path
        return urlunparse(url_parsed)

    url = base
    for add_on in add_ons:
        url = combine_single(url, add_on)
    return url


def read_file_or_url(url, **kwargs) -> Union["FileResponse", "UrlResponse"]:
    """Wrapper function around readurl to allow passing a file path as url.

    When url is not a local file path, passthrough any kwargs to readurl.

    In the case of parameter passthrough to readurl, default values for some
    parameters. See: call-signature of readurl in this module for param docs.
    """
    url = url.lstrip()
    if url.startswith("/"):
        url = "file://%s" % url
    if url.lower().startswith("file://"):
        if kwargs.get("data"):
            LOG.warning("Unable to post data to file resource %s", url)
        file_path = url[len("file://") :]
        try:
            with open(file_path, "rb") as fp:
                contents = fp.read()
        except IOError as e:
            code = e.errno
            if e.errno == ENOENT:
                code = NOT_FOUND
            raise UrlError(cause=e, code=code, headers=None, url=url) from e
        return FileResponse(file_path, contents=contents)
    else:
        return readurl(url, **kwargs)


# Made to have same accessors as UrlResponse so that the
# read_file_or_url can return this or that object and the
# 'user' of those objects will not need to know the difference.
class StringResponse:
    def __init__(self, contents, code=200):
        self.code = code
        self.headers = {}
        self.contents = contents
        self.url = None

    def ok(self, *args, **kwargs):
        if self.code != 200:
            return False
        return True

    def __str__(self):
        return self.contents.decode("utf-8")


class FileResponse(StringResponse):
    def __init__(self, path, contents, code=200):
        StringResponse.__init__(self, contents, code=code)
        self.url = path


class UrlResponse:
    def __init__(self, response: requests.Response):
        self._response = response

    @property
    def contents(self) -> bytes:
        if self._response.content is None:
            return b""
        return self._response.content

    @property
    def url(self):
        return self._response.url

    def ok(self, redirects_ok=False):
        upper = 300
        if redirects_ok:
            upper = 400
        if 200 <= self.code < upper:
            return True
        else:
            return False

    @property
    def headers(self):
        return self._response.headers

    @property
    def code(self):
        return self._response.status_code

    def __str__(self):
        return self._response.text

    def iter_content(
        self, chunk_size: Optional[int] = 1, decode_unicode: bool = False
    ) -> Iterator[bytes]:
        """Iterates over the response data.

        When stream=True is set on the request, this avoids reading the content
        at once into memory for large responses.

        :param chunk_size: Number of bytes it should read into memory.
        :param decode_unicode: If True, content will be decoded using the best
        available encoding based on the response.
        """
        yield from self._response.iter_content(chunk_size, decode_unicode)


class UrlError(IOError):
    def __init__(self, cause, code=None, headers=None, url=None):
        IOError.__init__(self, str(cause))
        self.cause = cause
        self.code = code
        self.headers = headers
        if self.headers is None:
            self.headers = {}
        self.url = url


def _get_ssl_args(url, ssl_details):
    ssl_args = {}
    scheme = urlparse(url).scheme
    if scheme == "https" and ssl_details:
        if "ca_certs" in ssl_details and ssl_details["ca_certs"]:
            ssl_args["verify"] = ssl_details["ca_certs"]
        else:
            ssl_args["verify"] = True
        if "cert_file" in ssl_details and "key_file" in ssl_details:
            ssl_args["cert"] = [
                ssl_details["cert_file"],
                ssl_details["key_file"],
            ]
        elif "cert_file" in ssl_details:
            ssl_args["cert"] = str(ssl_details["cert_file"])
    return ssl_args


def readurl(
    url,
    data=None,
    timeout=None,
    retries=0,
    sec_between=1,
    headers=None,
    headers_cb=None,
    headers_redact=None,
    ssl_details=None,
    check_status=True,
    allow_redirects=True,
    exception_cb=None,
    session=None,
    infinite=False,
    log_req_resp=True,
    request_method="",
    stream: bool = False,
) -> UrlResponse:
    """Wrapper around requests.Session to read the url and retry if necessary

    :param url: Mandatory url to request.
    :param data: Optional form data to post the URL. Will set request_method
        to 'POST' if present.
    :param timeout: Timeout in seconds to wait for a response. May be a tuple
        if specifying (connection timeout, read timeout).
    :param retries: Number of times to retry on exception if exception_cb is
        None or exception_cb returns True for the exception caught. Default is
        to fail with 0 retries on exception.
    :param sec_between: Default 1: amount of seconds passed to time.sleep
        between retries. None or -1 means don't sleep.
    :param headers: Optional dict of headers to send during request
    :param headers_cb: Optional callable returning a dict of values to send as
        headers during request
    :param headers_redact: Optional list of header names to redact from the log
    :param ssl_details: Optional dict providing key_file, ca_certs, and
        cert_file keys for use on in ssl connections.
    :param check_status: Optional boolean set True to raise when HTTPError
        occurs. Default: True.
    :param allow_redirects: Optional boolean passed straight to Session.request
        as 'allow_redirects'. Default: True.
    :param exception_cb: Optional callable which accepts the params
        msg and exception and returns a boolean True if retries are permitted.
    :param session: Optional exiting requests.Session instance to reuse.
    :param infinite: Bool, set True to retry indefinitely. Default: False.
    :param log_req_resp: Set False to turn off verbose debug messages.
    :param request_method: String passed as 'method' to Session.request.
        Typically GET, or POST. Default: POST if data is provided, GET
        otherwise.
    :param stream: if False, the response content will be immediately
    downloaded.
    """
    url = _cleanurl(url)
    req_args = {
        "url": url,
        "stream": stream,
    }
    req_args.update(_get_ssl_args(url, ssl_details))
    req_args["allow_redirects"] = allow_redirects
    if not request_method:
        request_method = "POST" if data else "GET"
    req_args["method"] = request_method
    if timeout is not None:
        if isinstance(timeout, tuple):
            req_args["timeout"] = timeout
        else:
            req_args["timeout"] = max(float(timeout), 0)
    if headers_redact is None:
        headers_redact = []
    manual_tries = 1
    if retries:
        manual_tries = max(int(retries) + 1, 1)

    def_headers = {
        "User-Agent": "Cloud-Init/%s" % (version.version_string()),
    }
    if headers:
        def_headers.update(headers)
    headers = def_headers

    if not headers_cb:

        def _cb(url):
            return headers

        headers_cb = _cb
    if data:
        req_args["data"] = data
    if sec_between is None:
        sec_between = -1

    excps = []
    # Handle retrying ourselves since the built-in support
    # doesn't handle sleeping between tries...
    # Infinitely retry if infinite is True
    for i in count() if infinite else range(manual_tries):
        req_args["headers"] = headers_cb(url)
        filtered_req_args = {}
        for (k, v) in req_args.items():
            if k == "data":
                continue
            if k == "headers" and headers_redact:
                matched_headers = [k for k in headers_redact if v.get(k)]
                if matched_headers:
                    filtered_req_args[k] = copy.deepcopy(v)
                    for key in matched_headers:
                        filtered_req_args[k][key] = REDACTED
            else:
                filtered_req_args[k] = v
        try:

            if log_req_resp:
                LOG.debug(
                    "[%s/%s] open '%s' with %s configuration",
                    i,
                    "infinite" if infinite else manual_tries,
                    url,
                    filtered_req_args,
                )

            if session is None:
                session = requests.Session()

            with session as sess:
                r = sess.request(**req_args)

            if check_status:
                r.raise_for_status()
            LOG.debug(
                "Read from %s (%s, %sb) after %s attempts",
                url,
                r.status_code,
                len(r.content),
                (i + 1),
            )
            # Doesn't seem like we can make it use a different
            # subclass for responses, so add our own backward-compat
            # attrs
            return UrlResponse(r)
        except exceptions.RequestException as e:
            if (
                isinstance(e, (exceptions.HTTPError))
                and hasattr(e, "response")
                and hasattr(  # This appeared in v 0.10.8
                    e.response, "status_code"
                )
            ):
                excps.append(
                    UrlError(
                        e,
                        code=e.response.status_code,
                        headers=e.response.headers,
                        url=url,
                    )
                )
            else:
                excps.append(UrlError(e, url=url))
                if isinstance(e, exceptions.SSLError):
                    # ssl exceptions are not going to get fixed by waiting a
                    # few seconds
                    break
            if exception_cb and not exception_cb(req_args.copy(), excps[-1]):
                # if an exception callback was given, it should return True
                # to continue retrying and False to break and re-raise the
                # exception
                break
            if (infinite and sec_between > 0) or (
                i + 1 < manual_tries and sec_between > 0
            ):

                if log_req_resp:
                    LOG.debug(
                        "Please wait %s seconds while we wait to try again",
                        sec_between,
                    )
                time.sleep(sec_between)

    raise excps[-1]


def _run_func_with_delay(
    func: Callable[..., Any],
    addr: str,
    timeout: int,
    event: threading.Event,
    delay: Optional[float] = None,
) -> Any:
    """Execute func with optional delay"""
    if delay:

        # event returns True iff the flag is set to true: indicating that
        # another thread has already completed successfully, no need to try
        # again - exit early
        if event.wait(timeout=delay):
            return
    return func(addr, timeout)


def dual_stack(
    func: Callable[..., Any],
    addresses: List[str],
    stagger_delay: float = 0.150,
    timeout: int = 10,
) -> Tuple:
    """execute multiple callbacks in parallel

    Run blocking func against two different addresses staggered with a
    delay. The first call to return successfully is returned from this
    function and remaining unfinished calls are cancelled if they have not
    yet started
    """
    return_result = None
    returned_address = None
    last_exception = None
    exceptions = []
    is_done = threading.Event()

    # future work: add cancel_futures to Python stdlib ThreadPoolExecutor
    # context manager implementation
    #
    # for now we don't use this feature since it only supports python >3.8
    # and doesn't provide a context manager and only marginal benefit
    executor = ThreadPoolExecutor(max_workers=len(addresses))
    try:
        futures = {
            executor.submit(
                _run_func_with_delay,
                func=func,
                addr=addr,
                timeout=timeout,
                event=is_done,
                delay=(i * stagger_delay),
            ): addr
            for i, addr in enumerate(addresses)
        }

        # handle returned requests in order of completion
        for future in as_completed(futures, timeout=timeout):

            returned_address = futures[future]
            return_exception = future.exception()
            if return_exception:
                last_exception = return_exception
                exceptions.append(last_exception)
            else:
                return_result = future.result()
                if return_result:

                    # communicate to other threads that they do not need to
                    # try: this thread has already succeeded
                    is_done.set()
                    return (returned_address, return_result)

        # No success, return the last exception but log them all for
        # debugging
        if last_exception:
            LOG.warning(
                "Exception(s) %s during request to "
                "%s, raising last exception",
                exceptions,
                returned_address,
            )
            raise last_exception
        else:
            LOG.error("Empty result for address %s", returned_address)
            raise ValueError("No result returned")

    # when max_wait expires, log but don't throw (retries happen)
    except TimeoutError:
        LOG.warning(
            "Timed out waiting for addresses: %s, "
            "exception(s) raised while waiting: %s",
            " ".join(addresses),
            " ".join(exceptions),  # type: ignore
        )
    finally:
        executor.shutdown(wait=False)

    return (returned_address, return_result)


def wait_for_url(
    urls,
    max_wait=None,
    timeout=None,
    status_cb: Callable = LOG.debug,  # some sources use different log levels
    headers_cb: Optional[Callable] = None,
    headers_redact=None,
    sleep_time: int = 1,
    exception_cb: Optional[Callable] = None,
    sleep_time_cb: Optional[Callable[[Any, int], int]] = None,
    request_method: str = "",
    connect_synchronously: bool = True,
    async_delay: float = 0.150,
):
    """
    urls:      a list of urls to try
    max_wait:  roughly the maximum time to wait before giving up
               The max time is *actually* len(urls)*timeout as each url will
               be tried once and given the timeout provided.
               a number <= 0 will always result in only one try
    timeout:   the timeout provided to urlopen
    status_cb: call method with string message when a url is not available
    headers_cb: call method with single argument of url to get headers
                for request.
    headers_redact: a list of header names to redact from the log
    exception_cb: call method with 2 arguments 'msg' (per status_cb) and
                  'exception', the exception that occurred.
    sleep_time_cb: call method with 2 arguments (response, loop_n) that
                   generates the next sleep time.
    request_method: indicate the type of HTTP request, GET, PUT, or POST
    connect_synchronously: if false, enables executing requests in parallel
    async_delay: delay before parallel metadata requests, see RFC 6555
    returns: tuple of (url, response contents), on failure, (False, None)

    the idea of this routine is to wait for the EC2 metadata service to
    come up.  On both Eucalyptus and EC2 we have seen the case where
    the instance hit the MD before the MD service was up.  EC2 seems
    to have permanently fixed this, though.

    In openstack, the metadata service might be painfully slow, and
    unable to avoid hitting a timeout of even up to 10 seconds or more
    (LP: #894279) for a simple GET.

    Offset those needs with the need to not hang forever (and block boot)
    on a system where cloud-init is configured to look for EC2 Metadata
    service but is not going to find one.  It is possible that the instance
    data host (169.254.169.254) may be firewalled off Entirely for a system,
    meaning that the connection will block forever unless a timeout is set.

    A value of None for max_wait will retry indefinitely.
    """

    def default_sleep_time(_, loop_number: int) -> int:
        return int(loop_number / 5) + 1

    def timeup(max_wait, start_time):
        """Check if time is up based on start time and max wait"""
        if max_wait is None:
            return False
        return (max_wait <= 0) or (time.time() - start_time > max_wait)

    def handle_url_response(response, url):
        """Map requests response code/contents to internal "UrlError" type"""
        if not response.contents:
            reason = "empty response [%s]" % (response.code)
            url_exc = UrlError(
                ValueError(reason),
                code=response.code,
                headers=response.headers,
                url=url,
            )
        elif not response.ok():
            reason = "bad status code [%s]" % (response.code)
            url_exc = UrlError(
                ValueError(reason),
                code=response.code,
                headers=response.headers,
                url=url,
            )
        else:
            reason = ""
            url_exc = None
        return (url_exc, reason)

    def read_url_handle_exceptions(
        url_reader_cb, urls, start_time, exc_cb, log_cb
    ):
        """Execute request, handle response, optionally log exception"""
        reason = ""
        url = None
        try:
            url, response = url_reader_cb(urls)
            url_exc, reason = handle_url_response(response, url)
            if not url_exc:
                return (url, response)
        except UrlError as e:
            reason = "request error [%s]" % e
            url_exc = e
        except Exception as e:
            reason = "unexpected error [%s]" % e
            url_exc = e
        time_taken = int(time.time() - start_time)
        max_wait_str = "%ss" % max_wait if max_wait else "unlimited"
        status_msg = "Calling '%s' failed [%s/%s]: %s" % (
            url,
            time_taken,
            max_wait_str,
            reason,
        )
        log_cb(status_msg)
        if exc_cb:
            # This can be used to alter the headers that will be sent
            # in the future, for example this is what the MAAS datasource
            # does.
            exc_cb(msg=status_msg, exception=url_exc)

    def read_url_cb(url, timeout):
        return readurl(
            url,
            headers={} if headers_cb is None else headers_cb(url),
            headers_redact=headers_redact,
            timeout=timeout,
            check_status=False,
            request_method=request_method,
        )

    def read_url_serial(start_time, timeout, exc_cb, log_cb):
        """iterate over list of urls, request each one and handle responses
        and thrown exceptions individually per url
        """

        def url_reader_serial(url):
            return (url, read_url_cb(url, timeout))

        for url in urls:
            now = time.time()
            if loop_n != 0:
                if timeup(max_wait, start_time):
                    return
                if (
                    max_wait is not None
                    and timeout
                    and (now + timeout > (start_time + max_wait))
                ):
                    # shorten timeout to not run way over max_time
                    timeout = int((start_time + max_wait) - now)

            out = read_url_handle_exceptions(
                url_reader_serial, url, start_time, exc_cb, log_cb
            )
            if out:
                return out

    def read_url_parallel(start_time, timeout, exc_cb, log_cb):
        """pass list of urls to dual_stack which sends requests in parallel
        handle response and exceptions of the first endpoint to respond
        """
        url_reader_parallel = partial(
            dual_stack,
            read_url_cb,
            stagger_delay=async_delay,
            timeout=timeout,
        )
        out = read_url_handle_exceptions(
            url_reader_parallel, urls, start_time, exc_cb, log_cb
        )
        if out:
            return out

    start_time = time.time()

    # Dual-stack support factored out serial and parallel execution paths to
    # allow the retry loop logic to exist separately from the http calls.
    # Serial execution should be fundamentally the same as before, but with a
    # layer of indirection so that the parallel dual-stack path may use the
    # same max timeout logic.
    do_read_url = (
        read_url_serial if connect_synchronously else read_url_parallel
    )

    calculate_sleep_time = sleep_time_cb or default_sleep_time

    loop_n: int = 0
    response = None
    while True:
        sleep_time = calculate_sleep_time(response, loop_n)

        url = do_read_url(start_time, timeout, exception_cb, status_cb)
        if url:
            address, response = url
            return (address, response.contents)

        if timeup(max_wait, start_time):
            break

        loop_n = loop_n + 1
        LOG.debug(
            "Please wait %s seconds while we wait to try again", sleep_time
        )
        time.sleep(sleep_time)

        # shorten timeout to not run way over max_time
        # timeout=0.0 causes exceptions in urllib, set to None if zero
        timeout = int((start_time + max_wait) - time.time()) or None

    LOG.error("Timed out, no response from urls: %s", urls)
    return False, None


class OauthUrlHelper:
    def __init__(
        self,
        consumer_key=None,
        token_key=None,
        token_secret=None,
        consumer_secret=None,
        skew_data_file="/run/oauth_skew.json",
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret or ""
        self.token_key = token_key
        self.token_secret = token_secret
        self.skew_data_file = skew_data_file
        self._do_oauth = True
        self.skew_change_limit = 5
        required = (self.token_key, self.token_secret, self.consumer_key)
        if not any(required):
            self._do_oauth = False
        elif not all(required):
            raise ValueError(
                "all or none of token_key, token_secret, or "
                "consumer_key can be set"
            )

        old = self.read_skew_file()
        self.skew_data = old or {}

    def read_skew_file(self):
        if self.skew_data_file and os.path.isfile(self.skew_data_file):
            with open(self.skew_data_file, mode="r") as fp:
                return json.load(fp)
        return None

    def update_skew_file(self, host, value):
        # this is not atomic
        if not self.skew_data_file:
            return
        cur = self.read_skew_file()
        if cur is None:
            cur = {}
        cur[host] = value
        with open(self.skew_data_file, mode="w") as fp:
            fp.write(json.dumps(cur))

    def exception_cb(self, msg, exception):
        if not (
            isinstance(exception, UrlError)
            and (exception.code == 403 or exception.code == 401)
        ):
            return

        if "date" not in exception.headers:
            LOG.warning("Missing header 'date' in %s response", exception.code)
            return

        date = exception.headers["date"]
        try:
            remote_time = time.mktime(parsedate(date))
        except Exception as e:
            LOG.warning("Failed to convert datetime '%s': %s", date, e)
            return

        skew = int(remote_time - time.time())
        host = urlparse(exception.url).netloc
        old_skew = self.skew_data.get(host, 0)
        if abs(old_skew - skew) > self.skew_change_limit:
            self.update_skew_file(host, skew)
            LOG.warning("Setting oauth clockskew for %s to %d", host, skew)
        self.skew_data[host] = skew

        return

    def headers_cb(self, url):
        if not self._do_oauth:
            return {}

        timestamp = None
        host = urlparse(url).netloc
        if self.skew_data and host in self.skew_data:
            timestamp = int(time.time()) + self.skew_data[host]

        return oauth_headers(
            url=url,
            consumer_key=self.consumer_key,
            token_key=self.token_key,
            token_secret=self.token_secret,
            consumer_secret=self.consumer_secret,
            timestamp=timestamp,
        )

    def _wrapped(self, wrapped_func, args, kwargs):
        kwargs["headers_cb"] = partial(
            self._headers_cb, kwargs.get("headers_cb")
        )
        kwargs["exception_cb"] = partial(
            self._exception_cb, kwargs.get("exception_cb")
        )
        return wrapped_func(*args, **kwargs)

    def wait_for_url(self, *args, **kwargs):
        return self._wrapped(wait_for_url, args, kwargs)

    def readurl(self, *args, **kwargs):
        return self._wrapped(readurl, args, kwargs)

    def _exception_cb(self, extra_exception_cb, msg, exception):
        ret = None
        try:
            if extra_exception_cb:
                ret = extra_exception_cb(msg, exception)
        finally:
            self.exception_cb(msg, exception)
        return ret

    def _headers_cb(self, extra_headers_cb, url):
        headers = {}
        if extra_headers_cb:
            headers = extra_headers_cb(url)
        headers.update(self.headers_cb(url))
        return headers


def oauth_headers(
    url, consumer_key, token_key, token_secret, consumer_secret, timestamp=None
):
    try:
        import oauthlib.oauth1 as oauth1
    except ImportError as e:
        raise NotImplementedError("oauth support is not available") from e

    if timestamp:
        timestamp = str(timestamp)
    else:
        timestamp = None

    client = oauth1.Client(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=token_key,
        resource_owner_secret=token_secret,
        signature_method=oauth1.SIGNATURE_PLAINTEXT,
        timestamp=timestamp,
    )
    _uri, signed_headers, _body = client.sign(url)
    return signed_headers
