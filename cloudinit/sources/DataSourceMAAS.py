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

import errno
import oauth.oauth as oauth
import os
import time
import urllib2

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper as uhelp
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

    def __str__(self):
        return "%s [%s]" % (util.obj_name(self), self.base_url)

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
                                                      self.md_headers)
            self.userdata_raw = userdata
            self.metadata = metadata
            return True
        except Exception:
            util.logexc(LOG, "Failed fetching metadata from url %s", url)
            return False

    def md_headers(self, url):
        mcfg = self.ds_cfg

        # If we are missing token_key, token_secret or consumer_key
        # then just do non-authed requests
        for required in ('token_key', 'token_secret', 'consumer_key'):
            if required not in mcfg:
                return {}

        consumer_secret = mcfg.get('consumer_secret', "")
        return oauth_headers(url=url,
                             consumer_key=mcfg['consumer_key'],
                             token_key=mcfg['token_key'],
                             token_secret=mcfg['token_secret'],
                             consumer_secret=consumer_secret)

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
        url = uhelp.wait_for_url(urls=urls, max_wait=max_wait,
                                 timeout=timeout, status_cb=LOG.warn,
                                 headers_cb=self.md_headers)

        if url:
            LOG.info("Using metadata source: '%s'", url)
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
            md[fname] = util.load_file(os.path.join(seed_d, fname))
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise

    return check_seed_contents(md, seed_d)


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
    base_url = "%s/%s" % (seed_url, version)
    files = {
        'local-hostname': "%s/%s" % (base_url, 'meta-data/local-hostname'),
        'instance-id': "%s/%s" % (base_url, 'meta-data/instance-id'),
        'public-keys': "%s/%s" % (base_url, 'meta-data/public-keys'),
        'user-data': "%s/%s" % (base_url, 'user-data'),
    }
    md = {}
    for (name, url) in files:
        if header_cb:
            headers = header_cb(url)
        else:
            headers = {}
        try:
            (resp, sc) = uhelp.readurl(url, headers=headers, timeout=timeout)
            if uhelp.ok_http_code(sc):
                md[name] = resp
        except urllib2.HTTPError as e:
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

    found = content.keys()
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
