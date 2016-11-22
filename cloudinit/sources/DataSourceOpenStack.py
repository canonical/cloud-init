# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

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


class DataSourceOpenStack(openstack.SourceMixin, sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceOpenStack, self).__init__(sys_cfg, distro, paths)
        self.metadata_address = None
        self.ssl_details = util.fetch_ssl_details(self.paths)
        self.version = None
        self.files = {}
        self.ec2_metadata = None

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

    def get_data(self, retries=5, timeout=5):
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
                                    kwargs={'ssl_details': self.ssl_details,
                                            'retries': retries,
                                            'timeout': timeout})
        except openstack.NonReadable:
            return False
        except (openstack.BrokenMetadata, IOError):
            util.logexc(LOG, "Broken metadata address %s",
                        self.metadata_address)
            return False

        self.dsmode = self._determine_dsmode([results.get('dsmode')])
        if self.dsmode == sources.DSMODE_DISABLED:
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
            self.vendordata_raw = sources.convert_vendordata(vd)
        except ValueError as e:
            LOG.warn("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        return True

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())


def read_metadata_service(base_url, ssl_details=None,
                          timeout=5, retries=5):
    reader = openstack.MetadataReader(base_url, ssl_details=ssl_details,
                                      timeout=timeout, retries=retries)
    return reader.read_v2()


# Used to match classes to dependencies
datasources = [
    (DataSourceOpenStack, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
