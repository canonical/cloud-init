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

from __future__ import print_function

import errno
import os
import time

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)
MD_VERSION = "2012-03-01"

BINARY_FIELDS = ('user-data',)


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
        self.oauth_helper = self._get_helper()

    def _get_helper(self):
        mcfg = self.ds_cfg
        # If we are missing token_key, token_secret or consumer_key
        # then just do non-authed requests
        for required in ('token_key', 'token_secret', 'consumer_key'):
            if required not in mcfg:
                return url_helper.OauthUrlHelper()

        return url_helper.OauthUrlHelper(
            consumer_key=mcfg['consumer_key'], token_key=mcfg['token_key'],
            token_secret=mcfg['token_secret'],
            consumer_secret=mcfg.get('consumer_secret'))

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
            # doing this here actually has a side affect of
            # getting oauth time-fix in place.  As no where else would
            # retry by default, so even if we could fix the timestamp
            # we would not.
            if not self.wait_for_metadata_service(url):
                return False

            self.base_url = url

            (userdata, metadata) = read_maas_seed_url(
                self.base_url, read_file_or_url=self.oauth_helper.readurl,
                paths=self.paths, retries=1)
            self.userdata_raw = userdata
            self.metadata = metadata
            return True
        except Exception:
            util.logexc(LOG, "Failed fetching metadata from url %s", url)
            return False

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
        url = self.oauth_helper.wait_for_url(
            urls=urls, max_wait=max_wait, timeout=timeout)

        if url:
            LOG.debug("Using metadata source: '%s'", url)
        else:
            LOG.critical("Giving up on md from %s after %i seconds",
                         urls, int(time.time() - starttime))

        return bool(url)


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
            md[fname] = util.load_file(os.path.join(seed_d, fname),
                                       decode=fname not in BINARY_FIELDS)
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    return check_seed_contents(md, seed_d)


def read_maas_seed_url(seed_url, read_file_or_url=None, timeout=None,
                       version=MD_VERSION, paths=None, retries=None):
    """
    Read the maas datasource at seed_url.
      read_file_or_url is a method that should provide an interface
      like util.read_file_or_url

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

    if read_file_or_url is None:
        read_file_or_url = util.read_file_or_url

    md = {}
    for name in file_order:
        url = files.get(name)
        if name == 'user-data':
            item_retries = 0
        else:
            item_retries = retries

        try:
            ssl_details = util.fetch_ssl_details(paths)
            resp = read_file_or_url(url, retries=item_retries,
                                    timeout=timeout, ssl_details=ssl_details)
            if resp.ok():
                if name in BINARY_FIELDS:
                    md[name] = resp.contents
                else:
                    md[name] = util.decode_binary(resp.contents)
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

    userdata = content.get('user-data', b"")
    md = {}
    for (key, val) in content.items():
        if key == 'user-data':
            continue
        md[key] = val

    return (userdata, md)


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

        oauth_helper = url_helper.OauthUrlHelper(**creds)

        def geturl(url):
            # the retry is to ensure that oauth timestamp gets fixed
            return oauth_helper.readurl(url, retries=1).contents

        def printurl(url):
            print("== %s ==\n%s\n" % (url, geturl(url).decode()))

        def crawl(url):
            if url.endswith("/"):
                for line in geturl(url).decode().splitlines():
                    if line.endswith("/"):
                        crawl("%s%s" % (url, line))
                    elif line == "meta-data":
                        # meta-data is a dir, it *should* end in a /
                        crawl("%s%s" % (url, "meta-data/"))
                    else:
                        printurl("%s%s" % (url, line))
            else:
                printurl(url)

        if args.subcmd == "check-seed":
            readurl = oauth_helper.readurl
            if args.url[0] == "/" or args.url.startswith("file://"):
                readurl = None
            (userdata, metadata) = read_maas_seed_url(
                args.url, version=args.apiver, read_file_or_url=readurl,
                retries=2)
            print("=== userdata ===")
            print(userdata.decode())
            print("=== metadata ===")
            pprint.pprint(metadata)

        elif args.subcmd == "get":
            printurl(args.url)

        elif args.subcmd == "crawl":
            if not args.url.endswith("/"):
                args.url = "%s/" % args.url
            crawl(args.url)

    main()
