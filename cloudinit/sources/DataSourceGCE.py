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
from cloudinit import util
from cloudinit import sources
from cloudinit import url_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://metadata.google.internal./computeMetadata/v1/'
}
REQUIRED_FIELDS = ('instance-id', 'availability-zone', 'local-hostname')


class DataSourceGCE(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata = dict()
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "GCE"], {}),
            BUILTIN_DS_CONFIG])
        self.metadata_address = self.ds_cfg['metadata_url']

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

        # url_map: (our-key, path, required)
        url_map = [
            ('instance-id', 'instance/id', True),
            ('availability-zone', 'instance/zone', True),
            ('local-hostname', 'instance/hostname', True),
            ('public-keys', 'project/attributes/sshKeys', False),
            ('user-data', 'instance/attributes/user-data', False),
        ]

        # if we cannot resolve the metadata server, then no point in trying
        if not util.is_resolvable_url(self.metadata_address):
            LOG.debug("%s is not resolvable", self.metadata_address)
            return False

        # iterate over url_map keys to get metadata items
        found = False
        for (mkey, path, required) in url_map:
            try:
                resp = url_helper.readurl(url=self.metadata_address + path,
                                          headers=headers)
                if resp.code == 200:
                    found = True
                    self.metadata[mkey] = resp.contents
                else:
                    if required:
                        msg = "required url %s returned code %s. not GCE"
                        if not found:
                            LOG.debug(msg, path, resp.code)
                        else:
                            LOG.warn(msg, path, resp.code)
                        return False
                    else:
                        self.metadata[mkey] = None
            except url_helper.UrlError as e:
                if required:
                    msg = "required url %s raised exception %s. not GCE"
                    if not found:
                        LOG.debug(msg, path, e)
                    else:
                        LOG.warn(msg, path, e)
                    return False
                msg = "Failed to get %s metadata item: %s."
                LOG.debug(msg, path, e)

                self.metadata[mkey] = None

        if self.metadata['public-keys']:
            lines = self.metadata['public-keys'].splitlines()
            self.metadata['public-keys'] = [self._trim_key(k) for k in lines]

        return found

    @property
    def launch_index(self):
        # GCE does not provide lauch_index property
        return None

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_public_ssh_keys(self):
        return self.metadata['public-keys']

    def get_hostname(self, fqdn=False, _resolve_ip=False):
        return self.metadata['local-hostname']

    def get_userdata_raw(self):
        return self.metadata['user-data']

    @property
    def availability_zone(self):
        return self.metadata['availability-zone']

# Used to match classes to dependencies
datasources = [
    (DataSourceGCE, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
