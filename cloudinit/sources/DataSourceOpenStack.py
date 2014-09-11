# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Yahoo! Inc.
#
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

import time

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

from cloudinit.sources.helpers import openstack

LOG = logging.getLogger(__name__)

# Various defaults/constants...
DEF_MD_URL = "http://169.254.169.254"
DEFAULT_IID = "iid-dsopenstack"
DEFAULT_METADATA = {
    "instance-id": DEFAULT_IID,
}
VALID_DSMODES = ("net", "disabled")


class DataSourceOpenStack(openstack.SourceMixin, sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceOpenStack, self).__init__(sys_cfg, distro, paths)
        self.dsmode = 'net'
        self.metadata_address = None
        self.ssl_details = util.fetch_ssl_details(self.paths)
        self.version = None
        self.files = {}
        self.ec2_metadata = None
        if not self.ds_cfg:
            self.ds_cfg = {}

    def __str__(self):
        root = sources.DataSource.__str__(self)
        mstr = "%s [%s,ver=%s]" % (root, self.dsmode, self.version)
        return mstr

    def _get_url_settings(self):
        # TODO(harlowja): this is shared with ec2 datasource, we should just
        # move it to a shared location instead...
        # Note: the defaults here are different though.

        # max_wait < 0 indicates do not wait
        max_wait = -1
        timeout = 10

        try:
            max_wait = int(self.ds_cfg.get("max_wait", max_wait))
        except Exception:
            util.logexc(LOG, "Failed to get max wait. using %s", max_wait)

        try:
            timeout = max(0, int(self.ds_cfg.get("timeout", timeout)))
        except Exception:
            util.logexc(LOG, "Failed to get timeout, using %s", timeout)
        return (max_wait, timeout)

    def wait_for_metadata_service(self):
        urls = self.ds_cfg.get("metadata_urls", [DEF_MD_URL])
        filtered = [x for x in urls if util.is_resolvable_url(x)]
        if set(filtered) != set(urls):
            LOG.debug("Removed the following from metadata urls: %s",
                      list((set(urls) - set(filtered))))
        if len(filtered):
            urls = filtered
        else:
            LOG.warn("Empty metadata url list! using default list")
            urls = [DEF_MD_URL]

        md_urls = []
        url2base = {}
        for url in urls:
            md_url = url_helper.combine_url(url, 'openstack')
            md_urls.append(md_url)
            url2base[md_url] = url

        (max_wait, timeout) = self._get_url_settings()
        start_time = time.time()
        avail_url = url_helper.wait_for_url(urls=md_urls, max_wait=max_wait,
                                            timeout=timeout)
        if avail_url:
            LOG.debug("Using metadata source: '%s'", url2base[avail_url])
        else:
            LOG.debug("Giving up on OpenStack md from %s after %s seconds",
                      md_urls, int(time.time() - start_time))

        self.metadata_address = url2base.get(avail_url)
        return bool(avail_url)

    def get_data(self):
        try:
            if not self.wait_for_metadata_service():
                return False
        except IOError:
            return False

        try:
            results = util.log_time(LOG.debug,
                                    'Crawl of openstack metadata service',
                                    read_metadata_service,
                                    args=[self.metadata_address],
                                    kwargs={'ssl_details': self.ssl_details})
        except openstack.NonReadable:
            return False
        except (openstack.BrokenMetadata, IOError):
            util.logexc(LOG, "Broken metadata address %s",
                        self.metadata_address)
            return False

        user_dsmode = results.get('dsmode', None)
        if user_dsmode not in VALID_DSMODES + (None,):
            LOG.warn("User specified invalid mode: %s", user_dsmode)
            user_dsmode = None
        if user_dsmode == 'disabled':
            return False

        md = results.get('metadata', {})
        md = util.mergemanydict([md, DEFAULT_METADATA])
        self.metadata = md
        self.ec2_metadata = results.get('ec2-metadata')
        self.userdata_raw = results.get('userdata')
        self.version = results['version']
        self.files.update(results.get('files', {}))

        vd = results.get('vendordata')
        self.vendordata_pure = vd
        try:
            self.vendordata_raw = openstack.convert_vendordata_json(vd)
        except ValueError as e:
            LOG.warn("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        return True


def read_metadata_service(base_url, ssl_details=None):
    reader = openstack.MetadataReader(base_url, ssl_details=ssl_details)
    return reader.read_v2()


# Used to match classes to dependencies
datasources = [
    (DataSourceOpenStack, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
