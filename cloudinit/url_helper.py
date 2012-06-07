import errno
import httplib
import time
import urllib
import urllib2

from StringIO import StringIO

from contextlib import closing

from cloudinit import log as logging
from cloudinit import shell as sh

LOG = logging.getLogger(__name__)


def ok_http_code(st):
    return st in xrange(200, 400)


def readurl(url, data=None, timeout=None, retries=0, sec_between=1, read_cb=None, headers=None):
    openargs = {}
    if timeout is not None:
        openargs['timeout'] = int(timeout)

    if data is None:
        req = urllib2.Request(url, headers=headers)
    else:
        req = urllib2.Request(url, data=urllib.urlencode(data), headers=headers)

    if retries <= 0:
        retries = 1

    last_excp = None
    LOG.debug("Attempting to read from %s with %s attempts to be performed", url, retries)
    for i in range(0, retries):
        try:
            with closing(urllib2.urlopen(req, **openargs)) as rh:
                ofh = StringIO()
                sh.pipe_in_out(rh, ofh, chunk_cb=read_cb)
                return (ofh.getvalue(), rh.getcode())
        except urllib2.HTTPError as e:
            last_excp = e
            LOG.exception("Failed at reading from %s.", url)
        except urllib2.URLError as e:
            # This can be a message string or
            # another exception instance (socket.error for remote URLs, OSError for local URLs).
            if (isinstance(e.reason, OSError) and
                e.reason.errno == errno.ENOENT):
                last_excp = e.reason
            else:
                last_excp = e
            LOG.exception("Failed at reading from %s.", url)
        LOG.debug("Please wait %s seconds while we wait to try again.", sec_between)
        time.sleep(sec_between)

    # Didn't work out
    LOG.warn("Failed downloading from %s after %s attempts", url, i + 1)
    if last_excp is not None:
        raise last_excp


def wait_for_url(urls, max_wait=None, timeout=None,
                 status_cb=None, headers_cb=None, sleep_time=1):
    """
    urls:      a list of urls to try
    max_wait:  roughly the maximum time to wait before giving up
               The max time is *actually* len(urls)*timeout as each url will
               be tried once and given the timeout provided.
    timeout:   the timeout provided to urllib2.urlopen
    status_cb: call method with string message when a url is not available
    headers_cb: call method with single argument of url to get headers
                for request.

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
    starttime = time.time()

    def nullstatus_cb(msg):
        return

    if status_cb is None:
        status_cb = nullstatus_cb

    def timeup(max_wait, starttime):
        return ((max_wait <= 0 or max_wait is None) or
                (time.time() - starttime > max_wait))

    loop_n = 0
    while True:
        sleeptime = int(loop_n / 5) + 1
        for url in urls:
            now = time.time()
            if loop_n != 0:
                if timeup(max_wait, starttime):
                    break
                if timeout and (now + timeout > (starttime + max_wait)):
                    # shorten timeout to not run way over max_time
                    timeout = int((starttime + max_wait) - now)

            reason = ""
            try:
                if headers_cb is not None:
                    headers = headers_cb(url)
                else:
                    headers = {}

                (resp, status_code) = readurl(url, headers=headers, timeout=timeout)
                if not resp:
                    reason = "empty response [%s]" % status_code
                elif not ok_http_code(status_code):
                    reason = "bad status code [%s]" % status_code
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

            status_cb("'%s' failed [%s/%ss]: %s" %
                      (url, int(time.time() - starttime), max_wait,
                       reason))

        if timeup(max_wait, starttime):
            break

        loop_n = loop_n + 1
        time.sleep(sleeptime)

    return False
