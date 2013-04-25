# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

from email.utils import parsedate
import errno
import oauth.oauth as oauth
import os
import time
import urllib2

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)
MD_VERSION = "2012-03-01"


class DataSourceMAAS(sources.DataSource):
    """
    DataSourceMAAS reads instance information from MAAS.
    Given a config metadata_url, and oauth tokens, it expects to find
    files under the root named:
      instance-id
      user-data
      hostname
    """
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.base_url = None
        self.seed_dir = os.path.join(paths.seed_dir, 'maas')
        self.oauth_clockskew = None

    def __str__(self):
        root = sources.DataSource.__str__(self)
        return "%s [%s]" % (root, self.base_url)

    def get_data(self):
        mcfg = self.ds_cfg

        try:
            (userdata, metadata) = read_maas_seed_dir(self.seed_dir)
            self.userdata_raw = userdata
            self.metadata = metadata
            self.base_url = self.seed_dir
            return True
        except MAASSeedDirNone:
            pass
        except MAASSeedDirMalformed as exc:
            LOG.warn("%s was malformed: %s" % (self.seed_dir, exc))
            raise

        # If there is no metadata_url, then we're not configured
        url = mcfg.get('metadata_url', None)
        if not url:
            return False

        try:
            if not self.wait_for_metadata_service(url):
                return False

            self.base_url = url

            (userdata, metadata) = read_maas_seed_url(self.base_url,
                                                      self._md_headers,
                                                      paths=self.paths)
            self.userdata_raw = userdata
            self.metadata = metadata
            return True
        except Exception:
            util.logexc(LOG, "Failed fetching metadata from url %s", url)
            return False

    def _md_headers(self, url):
        mcfg = self.ds_cfg

        # If we are missing token_key, token_secret or consumer_key
        # then just do non-authed requests
        for required in ('token_key', 'token_secret', 'consumer_key'):
            if required not in mcfg:
                return {}

        consumer_secret = mcfg.get('consumer_secret', "")

        timestamp = None
        if self.oauth_clockskew:
            timestamp = int(time.time()) + self.oauth_clockskew

        return oauth_headers(url=url,
                             consumer_key=mcfg['consumer_key'],
                             token_key=mcfg['token_key'],
                             token_secret=mcfg['token_secret'],
                             consumer_secret=consumer_secret,
                             timestamp=timestamp)

    def wait_for_metadata_service(self, url):
        mcfg = self.ds_cfg

        max_wait = 120
        try:
            max_wait = int(mcfg.get("max_wait", max_wait))
        except Exception:
            util.logexc(LOG, "Failed to get max wait. using %s", max_wait)

        if max_wait == 0:
            return False

        timeout = 50
        try:
            if timeout in mcfg:
                timeout = int(mcfg.get("timeout", timeout))
        except Exception:
            LOG.warn("Failed to get timeout, using %s" % timeout)

        starttime = time.time()
        check_url = "%s/%s/meta-data/instance-id" % (url, MD_VERSION)
        urls = [check_url]
        url = url_helper.wait_for_url(urls=urls, max_wait=max_wait,
                                      timeout=timeout,
                                      exception_cb=self._except_cb,
                                      headers_cb=self._md_headers)

        if url:
            LOG.debug("Using metadata source: '%s'", url)
        else:
            LOG.critical("Giving up on md from %s after %i seconds",
                         urls, int(time.time() - starttime))

        return bool(url)

    def _except_cb(self, msg, exception):
        if not (isinstance(exception, url_helper.UrlError) and
                (exception.code == 403 or exception.code == 401)):
            return

        if 'date' not in exception.headers:
            LOG.warn("Missing header 'date' in %s response", exception.code)
            return

        date = exception.headers['date']
        try:
            ret_time = time.mktime(parsedate(date))
        except Exception as e:
            LOG.warn("Failed to convert datetime '%s': %s", date, e)
            return

        self.oauth_clockskew = int(ret_time - time.time())
        LOG.warn("Setting oauth clockskew to %d", self.oauth_clockskew)
        return


def read_maas_seed_dir(seed_d):
    """
    Return user-data and metadata for a maas seed dir in seed_d.
    Expected format of seed_d are the following files:
      * instance-id
      * local-hostname
      * user-data
    """
    if not os.path.isdir(seed_d):
        raise MAASSeedDirNone("%s: not a directory")

    files = ('local-hostname', 'instance-id', 'user-data', 'public-keys')
    md = {}
    for fname in files:
        try:
            md[fname] = util.load_file(os.path.join(seed_d, fname))
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    return check_seed_contents(md, seed_d)


def read_maas_seed_url(seed_url, header_cb=None, timeout=None,
                       version=MD_VERSION, paths=None):
    """
    Read the maas datasource at seed_url.
      - header_cb is a method that should return a headers dictionary for
        a given url

    Expected format of seed_url is are the following files:
      * <seed_url>/<version>/meta-data/instance-id
      * <seed_url>/<version>/meta-data/local-hostname
      * <seed_url>/<version>/user-data
    """
    base_url = "%s/%s" % (seed_url, version)
    file_order = [
        'local-hostname',
        'instance-id',
        'public-keys',
        'user-data',
    ]
    files = {
        'local-hostname': "%s/%s" % (base_url, 'meta-data/local-hostname'),
        'instance-id': "%s/%s" % (base_url, 'meta-data/instance-id'),
        'public-keys': "%s/%s" % (base_url, 'meta-data/public-keys'),
        'user-data': "%s/%s" % (base_url, 'user-data'),
    }
    md = {}
    for name in file_order:
        url = files.get(name)
        if not header_cb:
            def _cb(url):
                return {}
            header_cb = _cb

        if name == 'user-data':
            retries = 0
        else:
            retries = None

        try:
            ssl_details = util.fetch_ssl_details(paths)
            resp = util.read_file_or_url(url, retries=retries,
                                         headers_cb=header_cb,
                                         timeout=timeout,
                                         ssl_details=ssl_details)
            if resp.ok():
                md[name] = str(resp)
            else:
                LOG.warn(("Fetching from %s resulted in"
                          " an invalid http code %s"), url, resp.code)
        except url_helper.UrlError as e:
            if e.code != 404:
                raise
    return check_seed_contents(md, seed_url)


def check_seed_contents(content, seed):
    """Validate if content is Is the content a dict that is valid as a
       return for a datasource.
       Either return a (userdata, metadata) tuple or
       Raise MAASSeedDirMalformed or MAASSeedDirNone
    """
    md_required = ('instance-id', 'local-hostname')
    if len(content) == 0:
        raise MAASSeedDirNone("%s: no data files found" % seed)

    found = list(content.keys())
    missing = [k for k in md_required if k not in found]
    if len(missing):
        raise MAASSeedDirMalformed("%s: missing files %s" % (seed, missing))

    userdata = content.get('user-data', "")
    md = {}
    for (key, val) in content.iteritems():
        if key == 'user-data':
            continue
        md[key] = val

    return (userdata, md)


def oauth_headers(url, consumer_key, token_key, token_secret, consumer_secret,
                  timestamp=None):
    consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
    token = oauth.OAuthToken(token_key, token_secret)

    if timestamp is None:
        ts = int(time.time())
    else:
        ts = timestamp

    params = {
        'oauth_version': "1.0",
        'oauth_nonce': oauth.generate_nonce(),
        'oauth_timestamp': ts,
        'oauth_token': token.key,
        'oauth_consumer_key': consumer.key,
    }
    req = oauth.OAuthRequest(http_url=url, parameters=params)
    req.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
                     consumer, token)
    return req.to_header()


class MAASSeedDirNone(Exception):
    pass


class MAASSeedDirMalformed(Exception):
    pass


# Used to match classes to dependencies
datasources = [
  (DataSourceMAAS, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    def main():
        """
        Call with single argument of directory or http or https url.
        If url is given additional arguments are allowed, which will be
        interpreted as consumer_key, token_key, token_secret, consumer_secret
        """
        import argparse
        import pprint

        parser = argparse.ArgumentParser(description='Interact with MAAS DS')
        parser.add_argument("--config", metavar="file",
            help="specify DS config file", default=None)
        parser.add_argument("--ckey", metavar="key",
            help="the consumer key to auth with", default=None)
        parser.add_argument("--tkey", metavar="key",
            help="the token key to auth with", default=None)
        parser.add_argument("--csec", metavar="secret",
            help="the consumer secret (likely '')", default="")
        parser.add_argument("--tsec", metavar="secret",
            help="the token secret to auth with", default=None)
        parser.add_argument("--apiver", metavar="version",
            help="the apiver to use ("" can be used)", default=MD_VERSION)

        subcmds = parser.add_subparsers(title="subcommands", dest="subcmd")
        subcmds.add_parser('crawl', help="crawl the datasource")
        subcmds.add_parser('get', help="do a single GET of provided url")
        subcmds.add_parser('check-seed', help="read andn verify seed at url")

        parser.add_argument("url", help="the data source to query")

        args = parser.parse_args()

        creds = {'consumer_key': args.ckey, 'token_key': args.tkey,
            'token_secret': args.tsec, 'consumer_secret': args.csec}

        if args.config:
            cfg = util.read_conf(args.config)
            if 'datasource' in cfg:
                cfg = cfg['datasource']['MAAS']
            for key in creds.keys():
                if key in cfg and creds[key] is None:
                    creds[key] = cfg[key]

        def geturl(url, headers_cb):
            req = urllib2.Request(url, data=None, headers=headers_cb(url))
            return (urllib2.urlopen(req).read())

        def printurl(url, headers_cb):
            print "== %s ==\n%s\n" % (url, geturl(url, headers_cb))

        def crawl(url, headers_cb=None):
            if url.endswith("/"):
                for line in geturl(url, headers_cb).splitlines():
                    if line.endswith("/"):
                        crawl("%s%s" % (url, line), headers_cb)
                    else:
                        printurl("%s%s" % (url, line), headers_cb)
            else:
                printurl(url, headers_cb)

        def my_headers(url):
            headers = {}
            if creds.get('consumer_key', None) is not None:
                headers = oauth_headers(url, **creds)
            return headers

        if args.subcmd == "check-seed":
            if args.url.startswith("http"):
                (userdata, metadata) = read_maas_seed_url(args.url,
                                                          header_cb=my_headers,
                                                          version=args.apiver)
            else:
                (userdata, metadata) = read_maas_seed_url(args.url)
            print "=== userdata ==="
            print userdata
            print "=== metadata ==="
            pprint.pprint(metadata)

        elif args.subcmd == "get":
            printurl(args.url, my_headers)

        elif args.subcmd == "crawl":
            if not args.url.endswith("/"):
                args.url = "%s/" % args.url
            crawl(args.url, my_headers)

    main()
