# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

import cloudinit.DataSource as DataSource

from cloudinit import seeddir as base_seeddir
from cloudinit import log
import cloudinit.util as util
import errno
import oauth.oauth as oauth
import os.path
import urllib2
import time


MD_VERSION = "2012-03-01"


class DataSourceMAAS(DataSource.DataSource):
    """
    DataSourceMAAS reads instance information from MAAS.
    Given a config metadata_url, and oauth tokens, it expects to find
    files under the root named:
      instance-id
      user-data
      hostname
    """
    seeddir = base_seeddir + '/maas'
    baseurl = None

    def __str__(self):
        return("DataSourceMAAS[%s]" % self.baseurl)

    def get_data(self):
        mcfg = self.ds_cfg

        try:
            (userdata, metadata) = read_maas_seed_dir(self.seeddir)
            self.userdata_raw = userdata
            self.metadata = metadata
            self.baseurl = self.seeddir
            return True
        except MAASSeedDirNone:
            pass
        except MAASSeedDirMalformed as exc:
            log.warn("%s was malformed: %s\n" % (self.seeddir, exc))
            raise

        try:
            # if there is no metadata_url, then we're not configured
            url = mcfg.get('metadata_url', None)
            if url == None:
                return False

            if not self.wait_for_metadata_service(url):
                return False

            self.baseurl = url

            (userdata, metadata) = read_maas_seed_url(self.baseurl,
                self.md_headers)
            self.userdata_raw = userdata
            self.metadata = metadata
            return True
        except Exception:
            util.logexc(log)
            return False

    def md_headers(self, url):
        mcfg = self.ds_cfg

        # if we are missing token_key, token_secret or consumer_key
        # then just do non-authed requests
        for required in ('token_key', 'token_secret', 'consumer_key'):
            if required not in mcfg:
                return({})

        consumer_secret = mcfg.get('consumer_secret', "")

        return(oauth_headers(url=url, consumer_key=mcfg['consumer_key'],
            token_key=mcfg['token_key'], token_secret=mcfg['token_secret'],
            consumer_secret=consumer_secret))

    def wait_for_metadata_service(self, url):
        mcfg = self.ds_cfg

        max_wait = 120
        try:
            max_wait = int(mcfg.get("max_wait", max_wait))
        except Exception:
            util.logexc(log)
            log.warn("Failed to get max wait. using %s" % max_wait)

        if max_wait == 0:
            return False

        timeout = 50
        try:
            timeout = int(mcfg.get("timeout", timeout))
        except Exception:
            util.logexc(log)
            log.warn("Failed to get timeout, using %s" % timeout)

        starttime = time.time()
        check_url = "%s/%s/meta-data/instance-id" % (url, MD_VERSION)
        url = util.wait_for_url(urls=[check_url], max_wait=max_wait,
            timeout=timeout, status_cb=log.warn,
            headers_cb=self.md_headers)

        if url:
            log.debug("Using metadata source: '%s'" % url)
        else:
            log.critical("giving up on md after %i seconds\n" %
                         int(time.time() - starttime))

        return (bool(url))


def read_maas_seed_dir(seed_d):
    """
    Return user-data and metadata for a maas seed dir in seed_d.
    Expected format of seed_d are the following files:
      * instance-id
      * local-hostname
      * user-data
    """
    files = ('local-hostname', 'instance-id', 'user-data', 'public-keys')
    md = {}

    if not os.path.isdir(seed_d):
        raise MAASSeedDirNone("%s: not a directory")

    for fname in files:
        try:
            with open(os.path.join(seed_d, fname)) as fp:
                md[fname] = fp.read()
                fp.close()
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    return(check_seed_contents(md, seed_d))


def read_maas_seed_url(seed_url, header_cb=None, timeout=None,
    version=MD_VERSION):
    """
    Read the maas datasource at seed_url.
    header_cb is a method that should return a headers dictionary that will
    be given to urllib2.Request()

    Expected format of seed_url is are the following files:
      * <seed_url>/<version>/meta-data/instance-id
      * <seed_url>/<version>/meta-data/local-hostname
      * <seed_url>/<version>/user-data
    """
    files = ('meta-data/local-hostname',
             'meta-data/instance-id',
             'meta-data/public-keys',
             'user-data')

    base_url = "%s/%s" % (seed_url, version)
    md = {}
    for fname in files:
        url = "%s/%s" % (base_url, fname)
        if header_cb:
            headers = header_cb(url)
        else:
            headers = {}

        try:
            req = urllib2.Request(url, data=None, headers=headers)
            resp = urllib2.urlopen(req, timeout=timeout)
            md[os.path.basename(fname)] = resp.read()
        except urllib2.HTTPError as e:
            if e.code != 404:
                raise

    return(check_seed_contents(md, seed_url))


def check_seed_contents(content, seed):
    """Validate if content is Is the content a dict that is valid as a
       return for a datasource.
       Either return a (userdata, metadata) tuple or
       Raise MAASSeedDirMalformed or MAASSeedDirNone
    """
    md_required = ('instance-id', 'local-hostname')
    found = content.keys()

    if len(content) == 0:
        raise MAASSeedDirNone("%s: no data files found" % seed)

    missing = [k for k in md_required if k not in found]
    if len(missing):
        raise MAASSeedDirMalformed("%s: missing files %s" % (seed, missing))

    userdata = content.get('user-data', "")
    md = {}
    for (key, val) in content.iteritems():
        if key == 'user-data':
            continue
        md[key] = val

    return(userdata, md)


def oauth_headers(url, consumer_key, token_key, token_secret, consumer_secret):
    consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
    token = oauth.OAuthToken(token_key, token_secret)
    params = {
        'oauth_version': "1.0",
        'oauth_nonce': oauth.generate_nonce(),
        'oauth_timestamp': int(time.time()),
        'oauth_token': token.key,
        'oauth_consumer_key': consumer.key,
    }
    req = oauth.OAuthRequest(http_url=url, parameters=params)
    req.sign_request(oauth.OAuthSignatureMethod_PLAINTEXT(),
        consumer, token)
    return(req.to_header())


class MAASSeedDirNone(Exception):
    pass


class MAASSeedDirMalformed(Exception):
    pass


datasources = [
  (DataSourceMAAS, (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
]


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))


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
            import yaml
            with open(args.config) as fp:
                cfg = yaml.load(fp)
            if 'datasource' in cfg:
                cfg = cfg['datasource']['MAAS']
            for key in creds.keys():
                if key in cfg and creds[key] == None:
                    creds[key] = cfg[key]

        def geturl(url, headers_cb):
            req = urllib2.Request(url, data=None, headers=headers_cb(url))
            return(urllib2.urlopen(req).read())

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
            if creds.get('consumer_key', None) != None:
                headers = oauth_headers(url, **creds)
            return headers

        if args.subcmd == "check-seed":
            if args.url.startswith("http"):
                (userdata, metadata) = read_maas_seed_url(args.url,
                    header_cb=my_headers, version=args.apiver)
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
