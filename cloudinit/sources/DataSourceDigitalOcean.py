# Author: Neal Shrader <neal@digitalocean.com>
# Author: Ben Howard  <bh@digitalocean.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# DigitalOcean Droplet API:
# https://developers.digitalocean.com/documentation/metadata/

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.digitalocean as do_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://169.254.169.254/metadata/v1.json',
}

# Wait for a up to a minute, retrying the meta-data server
# every 2 seconds.
MD_RETRIES = 30
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2
MD_USE_IPV4LL = True


class DataSourceDigitalOcean(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "DigitalOcean"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']
        self.retries = self.ds_cfg.get('retries', MD_RETRIES)
        self.timeout = self.ds_cfg.get('timeout', MD_TIMEOUT)
        self.use_ip4LL = self.ds_cfg.get('use_ip4LL', MD_USE_IPV4LL)
        self.wait_retry = self.ds_cfg.get('wait_retry', MD_WAIT_RETRY)
        self._network_config = None

    def _get_sysinfo(self):
        return do_helper.read_sysinfo()

    def get_data(self):
        (is_do, droplet_id) = self._get_sysinfo()

        # only proceed if we know we are on DigitalOcean
        if not is_do:
            return False

        LOG.info("Running on digital ocean. droplet_id=%s" % droplet_id)

        ipv4LL_nic = None
        if self.use_ip4LL:
            ipv4LL_nic = do_helper.assign_ipv4_link_local()

        md = do_helper.read_metadata(
            self.metadata_address, timeout=self.timeout,
            sec_between=self.wait_retry, retries=self.retries)

        self.metadata_full = md
        self.metadata['instance-id'] = md.get('droplet_id', droplet_id)
        self.metadata['local-hostname'] = md.get('hostname', droplet_id)
        self.metadata['interfaces'] = md.get('interfaces')
        self.metadata['public-keys'] = md.get('public_keys')
        self.metadata['availability_zone'] = md.get('region', 'default')
        self.vendordata_raw = md.get("vendor_data", None)
        self.userdata_raw = md.get("user_data", None)

        if ipv4LL_nic:
            do_helper.del_ipv4_link_local(ipv4LL_nic)

        return True

    def check_instance_id(self, sys_cfg):
        return sources.instance_id_matches_system_uuid(
            self.get_instance_id(), 'system-serial-number')

    @property
    def network_config(self):
        """Configure the networking. This needs to be done each boot, since
           the IP information may have changed due to snapshot and/or
           migration.
        """

        if self._network_config:
            return self._network_config

        interfaces = self.metadata.get('interfaces')
        LOG.debug(interfaces)
        if not interfaces:
            raise Exception("Unable to get meta-data from server....")

        nameservers = self.metadata_full['dns']['nameservers']
        self._network_config = do_helper.convert_network_configuration(
            interfaces, nameservers)
        return self._network_config


# Used to match classes to dependencies
datasources = [
    (DataSourceDigitalOcean, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
