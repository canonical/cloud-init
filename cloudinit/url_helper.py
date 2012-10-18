# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from contextlib import closing

import errno
import socket
import time
import urllib

from urllib3 import connectionpool
from urllib3 import util

from cloudinit import log as logging
from cloudinit import version

LOG = logging.getLogger(__name__)


class UrlResponse(object):
    def __init__(self, status_code, contents=None, headers=None):
        self._status_code = status_code
        self._contents = contents
        self._headers = headers

    @property
    def code(self):
        return self._status_code

    @property
    def contents(self):
        return self._contents

    @property
    def headers(self):
        return self._headers

    def __str__(self):
        if not self.contents:
            return ''
        else:
            return str(self.contents)

    def ok(self, redirects_ok=False):
        upper = 300
        if redirects_ok:
            upper = 400
        if self.code >= 200 and self.code < upper:
            return True
        else:
            return False


def readurl(url, data=None, timeout=None, retries=0,
            headers=None, ssl_details=None):
    req_args = {}
    p_url = util.parse_url(url)
    if p_url.scheme == 'https' and ssl_details:
        for k in ['key_file', 'cert_file', 'cert_reqs', 'ca_certs']:
            if k in ssl_details:
                req_args[k] = ssl_details[k]
    with closing(connectionpool.connection_from_url(url, **req_args)) as req_p:
        retries = max(int(retries), 0)
        attempts = retries + 1
        LOG.debug(("Attempting to open '%s' with %s attempts"
                   " (%s retries, timeout=%s) to be performed"),
                  url, attempts, retries, timeout)
        open_args = {
            'method': 'GET',
            'retries': retries,
            'redirect': False,
            'url': p_url.request_uri,
        }
        if data is not None:
            open_args['body'] = urllib.urlencode(data)
            open_args['method'] = 'POST'
        if not headers:
            headers = {
                'User-Agent': 'Cloud-Init/%s' % (version.version_string()),
            }
        open_args['headers'] = headers
        if timeout is not None:
            open_args['timeout'] = max(int(timeout), 0)
        r = req_p.urlopen(**open_args)
        return UrlResponse(r.status, r.data, r.headers)


def wait_for_url(urls, max_wait=None, timeout=None,
                 status_cb=None, headers_cb=None, sleep_time=1,
                 exception_cb=None):
    """
    urls:      a list of urls to try
    max_wait:  roughly the maximum time to wait before giving up
               The max time is *actually* len(urls)*timeout as each url will
               be tried once and given the timeout provided.
    timeout:   the timeout provided to urllib2.urlopen
    status_cb: call method with string message when a url is not available
    headers_cb: call method with single argument of url to get headers
                for request.
    exception_cb: call method with 2 arguments 'msg' (per status_cb) and
                  'exception', the exception that occurred.

    the idea of this routine is to wait for the EC2 metdata service to
    come up.  On both Eucalyptus and EC2 we have seen the case where
    the instance hit the MD before the MD service was up.  EC2 seems
    to have permenantely fixed this, though.

    In openstack, the metadata service might be painfully slow, and
    unable to avoid hitting a timeout of even up to 10 seconds or more
    (LP: #894279) for a simple GET.

    Offset those needs with the need to not hang forever (and block boot)
    on a system where cloud-init is configured to look for EC2 Metadata
    service but is not going to find one.  It is possible that the instance
    data host (169.254.169.254) may be firewalled off Entirely for a sytem,
    meaning that the connection will block forever unless a timeout is set.
    """
    start_time = time.time()

    def log_status_cb(msg, exc=None):
        LOG.debug(msg)

    if status_cb is None:
        status_cb = log_status_cb

    def timeup(max_wait, start_time):
        return ((max_wait <= 0 or max_wait is None) or
                (time.time() - start_time > max_wait))

    loop_n = 0
    while True:
        sleep_time = int(loop_n / 5) + 1
        for url in urls:
            now = time.time()
            if loop_n != 0:
                if timeup(max_wait, start_time):
                    break
                if timeout and (now + timeout > (start_time + max_wait)):
                    # shorten timeout to not run way over max_time
                    timeout = int((start_time + max_wait) - now)

            reason = ""
            try:
                if headers_cb is not None:
                    headers = headers_cb(url)
                else:
                    headers = {}

                resp = readurl(url, headers=headers, timeout=timeout)
                if not resp.contents:
                    reason = "empty response [%s]" % (resp.code)
                    e = ValueError(reason)
                elif not resp.ok():
                    reason = "bad status code [%s]" % (resp.code)
                    e = ValueError(reason)
                else:
                    return url
            except urllib2.HTTPError as e:
                reason = "http error [%s]" % e.code
            except urllib2.URLError as e:
                reason = "url error [%s]" % e.reason
            except socket.timeout as e:
                reason = "socket timeout [%s]" % e
            except Exception as e:
                reason = "unexpected error [%s]" % e

            time_taken = int(time.time() - start_time)
            status_msg = "Calling '%s' failed [%s/%ss]: %s" % (url,
                                                             time_taken,
                                                             max_wait, reason)
            status_cb(status_msg)
            if exception_cb:
                exception_cb(msg=status_msg, exception=e)

        if timeup(max_wait, start_time):
            break

        loop_n = loop_n + 1
        LOG.debug("Please wait %s seconds while we wait to try again",
                  sleep_time)
        time.sleep(sleep_time)

    return False
