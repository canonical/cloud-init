# vi: ts=4 expandtab
#
#    Author: Neal Shrader <neal@digitalocean.com>
#    Author: Ben Howard  <bh@digitalocean.com>
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

# DigitalOcean Droplet API:
# https://developers.digitalocean.com/documentation/metadata/

import json

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://169.254.169.254/metadata/v1.json',
}

# Wait for a up to a minute, retrying the meta-data server
# every 2 seconds.
MD_RETRIES = 30
MD_TIMEOUT = 2
MD_WAIT_RETRY = 2


class DataSourceDigitalOcean(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "DigitalOcean"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']
        self.retries = self.ds_cfg.get('retries', MD_RETRIES)
        self.timeout = self.ds_cfg.get('timeout', MD_TIMEOUT)
        self.wait_retry = self.ds_cfg.get('wait_retry', MD_WAIT_RETRY)

    def _get_sysinfo(self):
        # DigitalOcean embeds vendor ID and instance/droplet_id in the
        # SMBIOS information

        LOG.debug("checking if instance is a DigitalOcean droplet")

        # Detect if we are on DigitalOcean and return the Droplet's ID
        vendor_name = util.read_dmi_data("system-manufacturer")
        if vendor_name != "DigitalOcean":
            return (False, None)

        LOG.info("running on DigitalOcean")

        droplet_id = util.read_dmi_data("system-serial-number")
        if droplet_id:
            LOG.debug(("system identified via SMBIOS as DigitalOcean Droplet"
                       "{}").format(droplet_id))
        else:
            LOG.critical(("system identified via SMBIOS as a DigitalOcean "
                          "Droplet, but did not provide an ID. Please file a "
                          "support ticket at: "
                          "https://cloud.digitalocean.com/support/tickets/"
                          "new"))

        return (True, droplet_id)

    def get_data(self, apply_filter=False):
        (is_do, droplet_id) = self._get_sysinfo()

        # only proceed if we know we are on DigitalOcean
        if not is_do:
            return False

        LOG.debug("reading metadata from {}".format(self.metadata_address))
        response = url_helper.readurl(self.metadata_address,
                                      timeout=self.timeout,
                                      sec_between=self.wait_retry,
                                      retries=self.retries)

        contents = util.decode_binary(response.contents)
        decoded = json.loads(contents)

        self.metadata = decoded
        self.metadata['instance-id'] = decoded.get('droplet_id', droplet_id)
        self.metadata['local-hostname'] = decoded.get('hostname', droplet_id)
        self.vendordata_raw = decoded.get("vendor_data", None)
        self.userdata_raw = decoded.get("user_data", None)
        return True

    def get_public_ssh_keys(self):
        public_keys = self.metadata.get('public_keys', [])
        if isinstance(public_keys, list):
            return public_keys
        else:
            return [public_keys]

    @property
    def availability_zone(self):
        return self.metadata.get('region', 'default')

    @property
    def launch_index(self):
        return None

    def check_instance_id(self, sys_cfg):
        return sources.instance_id_matches_system_uuid(
            self.get_instance_id(), 'system-serial-number')


# Used to match classes to dependencies
datasources = [
    (DataSourceDigitalOcean, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
