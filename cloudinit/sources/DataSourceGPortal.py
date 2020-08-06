# Author: Alexander Birkner <alexander.birkner@g-portal.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.gportal as gportal_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://169.254.169.254/metadata/v1.json',
}


class DataSourceGPortal(sources.DataSource):
    dsname = 'GPortal'

    # Available server types
    ServerTypeBareMetal = 'BARE_METAL'
    ServerTypeVirtual = 'VIRTUAL'

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceGPortal, self).__init__(sys_cfg, distro, paths)

        self.ds_cfg = util.mergemanydict([self.ds_cfg, BUILTIN_DS_CONFIG])

        self.metadata_address = self.ds_cfg['metadata_url']

        self.retries = self.ds_cfg.get('retries', 30)
        self.timeout = self.ds_cfg.get('timeout', 5)
        self.wait_retry = self.ds_cfg.get('wait_retry', 2)

        self._network_config = None
        self._server_type = None

    def _get_data(self):
        LOG.info("Running on GPortal, downloading meta data now...")

        md = gportal_helper.load_metadata(
            self.metadata_address, timeout=self.timeout,
            sec_between=self.wait_retry, retries=self.retries)

        self.metadata_full = md
        self.metadata['instance-id'] = md.get('id')
        self.metadata['local-hostname'] = md.get('fqdn')
        self.metadata['interfaces'] = md.get('interfaces')
        self.metadata['routes'] = md.get('routes')
        self.metadata['public-keys'] = md.get('public_keys')
        self.metadata['availability_zone'] = md.get('region', 'unknown')
        self.metadata['nameservers'] = md.get('dns', {}).get('nameservers', [])
        self.vendordata_raw = md.get("vendor_data")
        self.userdata_raw = md.get("user_data")
        self._server_type = md.get('type', self.ServerTypeBareMetal)

        LOG.info("Detected GPortal server type: %s", self._server_type)
        return True

    def check_instance_id(self, sys_cfg):
        # Currently we don't have a way on bare metal nodes
        # to detect if the instance-id matches.
        if self._server_type == self.ServerTypeBareMetal:
            return True

        return sources.instance_id_matches_system_uuid(self.get_instance_id())

    @property
    def network_config(self):
        if self._network_config:
            return self._network_config

        interfaces = self.metadata.get('interfaces')

        if not interfaces:
            raise Exception("Unable to get meta-data from server....")

        nameservers = self.metadata.get('nameservers')

        routes = self.metadata.get('routes')
        self._network_config = gportal_helper.convert_network_configuration(
            interfaces, nameservers, routes)
        return self._network_config


# Used to match classes to dependencies
datasources = [
    (DataSourceGPortal, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
