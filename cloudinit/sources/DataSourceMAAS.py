# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from __future__ import print_function

import os
import time

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)
MD_VERSION = "2012-03-01"

DS_FIELDS = [
    # remote path, location in dictionary, binary data?, optional?
    ("meta-data/instance-id", 'meta-data/instance-id', False, False),
    ("meta-data/local-hostname", 'meta-data/local-hostname', False, False),
    ("meta-data/public-keys", 'meta-data/public-keys', False, True),
    ('meta-data/vendor-data', 'vendor-data', True, True),
    ('user-data', 'user-data', True, True),
]


class DataSourceMAAS(sources.DataSource):
    """
    DataSourceMAAS reads instance information from MAAS.
    Given a config metadata_url, and oauth tokens, it expects to find
    files under the root named:
      instance-id
      user-data
      hostname
      vendor-data
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
            self._set_data(self.seed_dir, read_maas_seed_dir(self.seed_dir))
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

            self._set_data(
                url, read_maas_seed_url(
                    url, read_file_or_url=self.oauth_helper.readurl,
                    paths=self.paths, retries=1))
            return True
        except Exception:
            util.logexc(LOG, "Failed fetching metadata from url %s", url)
            return False

    def _set_data(self, url, data):
        # takes a url for base_url and a tuple of userdata, metadata, vd.
        self.base_url = url
        ud, md, vd = data
        self.userdata_raw = ud
        self.metadata = md
        self.vendordata_pure = vd
        if vd:
            try:
                self.vendordata_raw = sources.convert_vendordata(vd)
            except ValueError as e:
                LOG.warn("Invalid content in vendor-data: %s", e)
                self.vendordata_raw = None

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
        if url.endswith("/"):
            url = url[:-1]
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
    if seed_d.startswith("file://"):
        seed_d = seed_d[7:]
    if not os.path.isdir(seed_d) or len(os.listdir(seed_d)) == 0:
        raise MAASSeedDirNone("%s: not a directory")

    # seed_dir looks in seed_dir, not seed_dir/VERSION
    return read_maas_seed_url("file://%s" % seed_d, version=None)


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
    If version is None, then <version>/ will not be used.
    """
    if read_file_or_url is None:
        read_file_or_url = util.read_file_or_url

    if seed_url.endswith("/"):
        seed_url = seed_url[:-1]

    md = {}
    for path, dictname, binary, optional in DS_FIELDS:
        if version is None:
            url = "%s/%s" % (seed_url, path)
        else:
            url = "%s/%s/%s" % (seed_url, version, path)
        try:
            ssl_details = util.fetch_ssl_details(paths)
            resp = read_file_or_url(url, retries=retries, timeout=timeout,
                                    ssl_details=ssl_details)
            if resp.ok():
                if binary:
                    md[path] = resp.contents
                else:
                    md[path] = util.decode_binary(resp.contents)
            else:
                LOG.warn(("Fetching from %s resulted in"
                          " an invalid http code %s"), url, resp.code)
        except url_helper.UrlError as e:
            if e.code == 404 and not optional:
                raise MAASSeedDirMalformed(
                    "Missing required %s: %s" % (path, e))
            elif e.code != 404:
                raise e

    return check_seed_contents(md, seed_url)


def check_seed_contents(content, seed):
    """Validate if dictionary content valid as a return for a datasource.
       Either return a (userdata, metadata, vendordata) tuple or
       Raise MAASSeedDirMalformed or MAASSeedDirNone
    """
    ret = {}
    missing = []
    for spath, dpath, _binary, optional in DS_FIELDS:
        if spath not in content:
            if not optional:
                missing.append(spath)
            continue

        if "/" in dpath:
            top, _, p = dpath.partition("/")
            if top not in ret:
                ret[top] = {}
            ret[top][p] = content[spath]
        else:
            ret[dpath] = content[spath]

    if len(ret) == 0:
        raise MAASSeedDirNone("%s: no data files found" % seed)

    if missing:
        raise MAASSeedDirMalformed("%s: missing files %s" % (seed, missing))

    vd_data = None
    if ret.get('vendor-data'):
        err = object()
        vd_data = util.load_yaml(ret.get('vendor-data'), default=err,
                                 allowed=(object))
        if vd_data is err:
            raise MAASSeedDirMalformed("vendor-data was not loadable as yaml.")

    return ret.get('user-data'), ret.get('meta-data'), vd_data


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
        import sys

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
                            help="the apiver to use ("" can be used)",
                            default=MD_VERSION)

        subcmds = parser.add_subparsers(title="subcommands", dest="subcmd")
        for (name, help) in (('crawl', 'crawl the datasource'),
                             ('get', 'do a single GET of provided url'),
                             ('check-seed', 'read and verify seed at url')):
            p = subcmds.add_parser(name, help=help)
            p.add_argument("url", help="the datasource url", nargs='?',
                           default=None)

        args = parser.parse_args()

        creds = {'consumer_key': args.ckey, 'token_key': args.tkey,
                 'token_secret': args.tsec, 'consumer_secret': args.csec}

        if args.config is None:
            for fname in ('91_kernel_cmdline_url', '90_dpkg_maas'):
                fpath = "/etc/cloud/cloud.cfg.d/" + fname + ".cfg"
                if os.path.exists(fpath) and os.access(fpath, os.R_OK):
                    sys.stderr.write("Used config in %s.\n" % fpath)
                    args.config = fpath

        if args.config:
            cfg = util.read_conf(args.config)
            if 'datasource' in cfg:
                cfg = cfg['datasource']['MAAS']
            for key in creds.keys():
                if key in cfg and creds[key] is None:
                    creds[key] = cfg[key]
            if args.url is None and 'metadata_url' in cfg:
                args.url = cfg['metadata_url']

        if args.url is None:
            sys.stderr.write("Must provide a url or a config with url.\n")
            sys.exit(1)

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
            sys.stderr.write("Checking seed at %s\n" % args.url)
            readurl = oauth_helper.readurl
            if args.url[0] == "/" or args.url.startswith("file://"):
                (userdata, metadata, vd) = read_maas_seed_dir(args.url)
            else:
                (userdata, metadata, vd) = read_maas_seed_url(
                    args.url, version=args.apiver, read_file_or_url=readurl,
                    retries=2)
            print("=== user-data ===")
            print("N/A" if userdata is None else userdata.decode())
            print("=== meta-data ===")
            pprint.pprint(metadata)
            print("=== vendor-data ===")
            pprint.pprint("N/A" if vd is None else vd)

        elif args.subcmd == "get":
            printurl(args.url)

        elif args.subcmd == "crawl":
            if not args.url.endswith("/"):
                args.url = "%s/" % args.url
            crawl(args.url)

    main()

# vi: ts=4 expandtab
