# Copyright (C) 2014 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import time

from cloudinit import log as logging
from cloudinit.net.dhcp import EphemeralDHCPv4, NoDHCPLeaseError
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

# OpenStack DMI constants
DMI_PRODUCT_NOVA = 'OpenStack Nova'
DMI_PRODUCT_COMPUTE = 'OpenStack Compute'
VALID_DMI_PRODUCT_NAMES = [DMI_PRODUCT_NOVA, DMI_PRODUCT_COMPUTE]
DMI_ASSET_TAG_OPENTELEKOM = 'OpenTelekomCloud'
VALID_DMI_ASSET_TAGS = [DMI_ASSET_TAG_OPENTELEKOM]


class DataSourceOpenStack(openstack.SourceMixin, sources.DataSource):

    dsname = "OpenStack"

    _network_config = sources.UNSET  # Used to cache calculated network cfg v1

    # Whether we want to get network configuration from the metadata service.
    perform_dhcp_setup = False

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceOpenStack, self).__init__(sys_cfg, distro, paths)
        self.metadata_address = None
        self.ssl_details = util.fetch_ssl_details(self.paths)
        self.version = None
        self.files = {}
        self.ec2_metadata = sources.UNSET
        self.network_json = sources.UNSET

    def __str__(self):
        root = sources.DataSource.__str__(self)
        mstr = "%s [%s,ver=%s]" % (root, self.dsmode, self.version)
        return mstr

    def wait_for_metadata_service(self):
        urls = self.ds_cfg.get("metadata_urls", [DEF_MD_URL])
        filtered = [x for x in urls if util.is_resolvable_url(x)]
        if set(filtered) != set(urls):
            LOG.debug("Removed the following from metadata urls: %s",
                      list((set(urls) - set(filtered))))
        if len(filtered):
            urls = filtered
        else:
            LOG.warning("Empty metadata url list! using default list")
            urls = [DEF_MD_URL]

        md_urls = []
        url2base = {}
        for url in urls:
            md_url = url_helper.combine_url(url, 'openstack')
            md_urls.append(md_url)
            url2base[md_url] = url

        url_params = self.get_url_params()
        start_time = time.time()
        avail_url = url_helper.wait_for_url(
            urls=md_urls, max_wait=url_params.max_wait_seconds,
            timeout=url_params.timeout_seconds)
        if avail_url:
            LOG.debug("Using metadata source: '%s'", url2base[avail_url])
        else:
            LOG.debug("Giving up on OpenStack md from %s after %s seconds",
                      md_urls, int(time.time() - start_time))

        self.metadata_address = url2base.get(avail_url)
        return bool(avail_url)

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still valid
        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    @property
    def network_config(self):
        """Return a network config dict for rendering ENI or netplan files."""
        if self._network_config != sources.UNSET:
            return self._network_config

        # RELEASE_BLOCKER: SRU to Xenial and Artful SRU should not provide
        # network_config by default unless configured in /etc/cloud/cloud.cfg*.
        # Patch Xenial and Artful before release to default to False.
        if util.is_false(self.ds_cfg.get('apply_network_config', True)):
            self._network_config = None
            return self._network_config
        if self.network_json == sources.UNSET:
            # this would happen if get_data hadn't been called. leave as UNSET
            LOG.warning(
                'Unexpected call to network_config when network_json is None.')
            return None

        LOG.debug('network config provided via network_json')
        self._network_config = openstack.convert_net_json(
            self.network_json, known_macs=None)
        return self._network_config

    def _get_data(self):
        """Crawl metadata, parse and persist that data for this instance.

        @return: True when metadata discovered indicates OpenStack datasource.
            False when unable to contact metadata service or when metadata
            format is invalid or disabled.
        """
        if not detect_openstack():
            return False
        if self.perform_dhcp_setup:  # Setup networking in init-local stage.
            try:
                with EphemeralDHCPv4(self.fallback_interface):
                    results = util.log_time(
                        logfunc=LOG.debug, msg='Crawl of metadata service',
                        func=self._crawl_metadata)
            except (NoDHCPLeaseError, sources.InvalidMetaDataException) as e:
                util.logexc(LOG, str(e))
                return False
        else:
            try:
                results = self._crawl_metadata()
            except sources.InvalidMetaDataException as e:
                util.logexc(LOG, str(e))
                return False

        self.dsmode = self._determine_dsmode([results.get('dsmode')])
        if self.dsmode == sources.DSMODE_DISABLED:
            return False
        md = results.get('metadata', {})
        md = util.mergemanydict([md, DEFAULT_METADATA])
        self.metadata = md
        self.ec2_metadata = results.get('ec2-metadata')
        self.network_json = results.get('networkdata')
        self.userdata_raw = results.get('userdata')
        self.version = results['version']
        self.files.update(results.get('files', {}))

        vd = results.get('vendordata')
        self.vendordata_pure = vd
        try:
            self.vendordata_raw = sources.convert_vendordata(vd)
        except ValueError as e:
            LOG.warning("Invalid content in vendor-data: %s", e)
            self.vendordata_raw = None

        return True

    def _crawl_metadata(self):
        """Crawl metadata service when available.

        @returns: Dictionary with all metadata discovered for this datasource.
        @raise: InvalidMetaDataException on unreadable or broken
            metadata.
        """
        try:
            if not self.wait_for_metadata_service():
                raise sources.InvalidMetaDataException(
                    'No active metadata service found')
        except IOError as e:
            raise sources.InvalidMetaDataException(
                'IOError contacting metadata service: {error}'.format(
                    error=str(e)))

        url_params = self.get_url_params()

        try:
            result = util.log_time(
                LOG.debug, 'Crawl of openstack metadata service',
                read_metadata_service, args=[self.metadata_address],
                kwargs={'ssl_details': self.ssl_details,
                        'retries': url_params.num_retries,
                        'timeout': url_params.timeout_seconds})
        except openstack.NonReadable as e:
            raise sources.InvalidMetaDataException(str(e))
        except (openstack.BrokenMetadata, IOError):
            msg = 'Broken metadata address {addr}'.format(
                addr=self.metadata_address)
            raise sources.InvalidMetaDataException(msg)
        return result


class DataSourceOpenStackLocal(DataSourceOpenStack):
    """Run in init-local using a dhcp discovery prior to metadata crawl.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """

    perform_dhcp_setup = True  # Get metadata network config if present


def read_metadata_service(base_url, ssl_details=None,
                          timeout=5, retries=5):
    reader = openstack.MetadataReader(base_url, ssl_details=ssl_details,
                                      timeout=timeout, retries=retries)
    return reader.read_v2()


def detect_openstack():
    """Return True when a potential OpenStack platform is detected."""
    if not util.is_x86():
        return True  # Non-Intel cpus don't properly report dmi product names
    product_name = util.read_dmi_data('system-product-name')
    if product_name in VALID_DMI_PRODUCT_NAMES:
        return True
    elif util.read_dmi_data('chassis-asset-tag') in VALID_DMI_ASSET_TAGS:
        return True
    elif util.get_proc_env(1).get('product_name') == DMI_PRODUCT_NOVA:
        return True
    return False


# Used to match classes to dependencies
datasources = [
    (DataSourceOpenStackLocal, (sources.DEP_FILESYSTEM,)),
    (DataSourceOpenStack, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
