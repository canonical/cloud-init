# vi: ts=4 expandtab
#
#    Author: Vaidas Jablonskis <jablonskis@gmail.com>
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
from cloudinit import sources
from cloudinit import url_helper

LOG = logging.getLogger(__name__)

MD_URL = 'http://metadata/computeMetadata/v1/'


class DataSourceGCE(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata_address = MD_URL
        self.metadata = {}

    # GCE takes sshKeys attribute in the format of '<user>:<public_key>'
    # so we have to trim each key to remove the username part
    def _trim_key(self, public_key):
        try:
            index = public_key.index(':')
            if index > 0:
                return public_key[(index + 1):]
        except:
            return public_key

    def get_data(self):
        # GCE metadata server requires a custom header since v1
        headers = {'X-Google-Metadata-Request': True}

        url_map = {
            'instance-id': self.metadata_address + 'instance/id',
            'availability-zone': self.metadata_address + 'instance/zone',
            'public-keys': self.metadata_address + 'project/attributes/sshKeys',
            'local-hostname': self.metadata_address + 'instance/hostname',
        }

        for mkey in url_map.iterkeys():
            resp = url_helper.readurl(url=url_map[mkey], headers=headers)
            if resp.ok():
                if mkey == 'public-keys':
                    pub_keys = [self._trim_key(k) for k in resp.contents.splitlines()]
                    self.metadata[mkey] = pub_keys
                else:
                    self.metadata[mkey] = resp.contents
            else:
                self.metadata[mkey] = None
                return False
        return True

    @property
    def launch_index(self):
        # GCE does not provide lauch_index property
        return None

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_public_ssh_keys(self):
        return self.metadata['public-keys']

    def get_hostname(self, fqdn=False):
        return self.metadata['local-hostname']

    def get_userdata_raw(self):
        return None

    @property
    def availability_zone(self):
        return self.metadata['instance-zone']

# Used to match classes to dependencies
datasources = [
    (DataSourceGCE, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
