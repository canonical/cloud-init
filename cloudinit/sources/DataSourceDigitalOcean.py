# vi: ts=4 expandtab
#
#    Author: Neal Shrader <neal@digitalocean.com>
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

from cloudinit import log as logging
from cloudinit import util
from cloudinit import sources
from cloudinit import ec2_utils

import functools


LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://169.254.169.254/metadata/v1/',
    'mirrors_url': 'http://mirrors.digitalocean.com/'
}
MD_RETRIES = 0
MD_TIMEOUT = 1


class DataSourceDigitalOcean(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "DigitalOcean"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']

        if self.ds_cfg.get('retries'):
            self.retries = self.ds_cfg['retries']
        else:
            self.retries = MD_RETRIES

        if self.ds_cfg.get('timeout'):
            self.timeout = self.ds_cfg['timeout']
        else:
            self.timeout = MD_TIMEOUT

    def get_data(self):
        caller = functools.partial(util.read_file_or_url,
                                   timeout=self.timeout, retries=self.retries)

        def mcaller(url):
            return caller(url).contents

        md = ec2_utils.MetadataMaterializer(mcaller(self.metadata_address),
                                            base_url=self.metadata_address,
                                            caller=mcaller)

        self.metadata = md.materialize()

        if self.metadata.get('id'):
            return True
        else:
            return False

    def get_userdata_raw(self):
        return "\n".join(self.metadata['user-data'])

    def get_vendordata_raw(self):
        return "\n".join(self.metadata['vendor-data'])

    def get_public_ssh_keys(self):
        public_keys = self.metadata['public-keys']
        if isinstance(public_keys, list):
            return public_keys
        else:
            return [public_keys]

    @property
    def availability_zone(self):
        return self.metadata['region']

    def get_instance_id(self):
        return self.metadata['id']

    def get_hostname(self, fqdn=False, resolve_ip=False):
        return self.metadata['hostname']

    def get_package_mirror_info(self):
        return self.ds_cfg['mirrors_url']

    @property
    def launch_index(self):
        return None

# Used to match classes to dependencies
datasources = [
  (DataSourceDigitalOcean, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
  ]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
