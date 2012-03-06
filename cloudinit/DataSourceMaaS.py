# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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
import socket
import urllib2
import time


class DataSourceMaaS(DataSource.DataSource):
    """
    DataSourceMaaS reads instance information from MaaS.
    Given a config metadata_url, and oauth tokens, it expects to find
    files under the root named:
      instance-id
      user-data
      hostname
    """
    seeddir = base_seeddir + '/maas'
    baseurl = None

    def __str__(self):
        return("DataSourceMaaS[%s]" % self.baseurl)

    def get_data(self):
        mcfg = self.ds_cfg

        try:
            (userdata, metadata) = read_maas_seed_dir(self.seeddir)
            self.userdata_raw = userdata
            self.metadata = metadata
            self.baseurl = self.seeddir
            return True
        except MaasSeedDirNone:
            pass
        except MaasSeedDirMalformed as exc:
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
        check_url = "%s/instance-id" % url
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
      * hostname
      * user-data
    """
    md_required = set(('hostname', 'instance-id'))
    files = md_required.union(set(('userdata',)))
    userdata = None
    md = {}

    if not os.path.isdir(seed_d):
        raise MaasSeedDirNone("%s: not a directory")

    for fname in files:
        try:
            with open(os.path.join(seed_d, fname)) as fp:
                if fname == 'userdata':
                    userdata = fp.read()
                else:
                    md[fname] = fp.read()
                fp.close()
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    if userdata == None and len(md) == 0:
        raise MaasSeedDirNone("%s: no data files found" % seed_d)

    if userdata == None:
        raise MaasSeedDirMalformed("%s: missing userdata" % seed_d)

    missing = md_required - set(md.keys())
    if len(missing):
        raise MaasSeedDirMalformed("%s: missing files %s" %
            (seed_d, str(missing)))

    return(userdata, md)


def read_maas_seed_url(seed_url, header_cb=None):
    """
    Read the maas datasource at seed_url.
    header_cb is a method that should return a headers dictionary that will
    be given to urllib2.Request()

    Expected format of seed_url is are the following files:
      * <seed_url>/instance-id
      * <seed_url>/hostname
      * <seed_url>/user-data
    """
    userdata = ""
    metadata = {'instance-id': 'i-maas-url', 'hostname': 'maas-url-hostname'}

    return(userdata, metadata)


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


class MaasSeedDirNone(Exception):
    pass


class MaasSeedDirMalformed(Exception):
    pass


datasources = [
  (DataSourceMaaS, (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
]


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return(DataSource.list_from_depends(depends, datasources))
