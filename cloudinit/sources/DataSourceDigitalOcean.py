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
from cloudinit import url_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://169.254.169.254/metadata/v1',
    'mirrors_url': 'http://mirrors.digitalocean.com/'
}

class DataSourceDigitalOcean(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "DigitalOcean"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']
        self.retries = 3
        self.timeout = 1

    def get_data(self):
        url_map = [
               ('user-data', '/user-data'),
               ('vendor-data', '/vendor-data'),
               ('public-keys', '/public-keys'),
               ('region', '/region'),
               ('id', '/id'),
               ('hostname', '/hostname'),
        ]

        found = False
        for (key, path) in url_map:
            try:
                resp = url_helper.readurl(url=self.metadata_address + path,
                                          timeout=self.timeout,
                                          retries=self.retries)
                if resp.code == 200:
                    found = True
                    self.metadata[key] = resp.contents
                else:
                    LOG.warn("Path: %s returned %s", path, resp.code)
                    return False
            except url_helper.UrlError as e:
                LOG.warn("Path: %s raised exception: %s", path, e)
                return False

        return found

    def get_userdata_raw(self):
        return self.metadata['user-data']

    def get_vendordata_raw(self):
	return self.metadata['vendor-data']

    def get_public_ssh_keys(self):
	return self.metadata['public-keys'].splitlines()

    @property
    def availability_zone(self):
        return self.metadata['region']

    def get_instance_id(self):
        return self.metadata['id']

    def get_hostname(self, fqdn=False):
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
