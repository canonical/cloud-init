# Author: Jonas Keidel <jonas.keidel@hetzner.com>
# Author: Markus Schade <markus.schade@hetzner.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
#
"""Hetzner Cloud API Documentation.
   https://docs.hetzner.cloud/"""

from cloudinit import log as logging
from cloudinit import net as cloudnet
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.hetzner as hc_helper

LOG = logging.getLogger(__name__)

BASE_URL_V1 = 'http://169.254.169.254/hetzner/v1'

BUILTIN_DS_CONFIG = {
    'metadata_url': BASE_URL_V1 + '/metadata',
    'userdata_url': BASE_URL_V1 + '/userdata',
}

MD_RETRIES = 60
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2


class DataSourceHetzner(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.distro = distro
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "Hetzner"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']
        self.userdata_address = self.ds_cfg['userdata_url']
        self.retries = self.ds_cfg.get('retries', MD_RETRIES)
        self.timeout = self.ds_cfg.get('timeout', MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get('wait_retry', MD_WAIT_RETRY)
        self._network_config = None
        self.dsmode = sources.DSMODE_NETWORK

    def get_data(self):
        if not on_hetzner():
            return False
        nic = cloudnet.find_fallback_nic()
        with cloudnet.EphemeralIPv4Network(nic, "169.254.0.1", 16,
                                           "169.254.255.255"):
            md = hc_helper.read_metadata(
                self.metadata_address, timeout=self.timeout,
                sec_between=self.wait_retry, retries=self.retries)
            ud = hc_helper.read_userdata(
                self.userdata_address, timeout=self.timeout,
                sec_between=self.wait_retry, retries=self.retries)

        self.userdata_raw = ud
        self.metadata_full = md

        """hostname is name provided by user at launch.  The API enforces
        it is a valid hostname, but it is not guaranteed to be resolvable
        in dns or fully qualified."""
        self.metadata['instance-id'] = md['instance-id']
        self.metadata['local-hostname'] = md['hostname']
        self.metadata['network-config'] = md.get('network-config', None)
        self.metadata['public-keys'] = md.get('public-keys', None)
        self.vendordata_raw = md.get("vendor_data", None)

        return True

    @property
    def network_config(self):
        """Configure the networking. This needs to be done each boot, since
           the IP information may have changed due to snapshot and/or
           migration.
        """

        if self._network_config:
            return self._network_config

        _net_config = self.metadata['network-config']
        if not _net_config:
            raise Exception("Unable to get meta-data from server....")

        self._network_config = _net_config

        return self._network_config


def on_hetzner():
    return util.read_dmi_data('system-manufacturer') == "Hetzner"


# Used to match classes to dependencies
datasources = [
    (DataSourceHetzner, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
