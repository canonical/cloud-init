# Author: Vaidas Jablonskis <jablonskis@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from base64 import b64decode

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'http://metadata.google.internal/computeMetadata/v1/'
}
REQUIRED_FIELDS = ('instance-id', 'availability-zone', 'local-hostname')


class GoogleMetadataFetcher(object):
    headers = {'X-Google-Metadata-Request': 'True'}

    def __init__(self, metadata_address):
        self.metadata_address = metadata_address

    def get_value(self, path, is_text):
        value = None
        try:
            resp = url_helper.readurl(url=self.metadata_address + path,
                                      headers=self.headers)
        except url_helper.UrlError as exc:
            msg = "url %s raised exception %s"
            LOG.debug(msg, path, exc)
        else:
            if resp.code == 200:
                if is_text:
                    value = util.decode_binary(resp.contents)
                else:
                    value = resp.contents
            else:
                LOG.debug("url %s returned code %s", path, resp.code)
        return value


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
        except Exception:
            return public_key

    def get_data(self):
        # url_map: (our-key, path, required, is_text)
        url_map = [
            ('instance-id', ('instance/id',), True, True),
            ('availability-zone', ('instance/zone',), True, True),
            ('local-hostname', ('instance/hostname',), True, True),
            ('public-keys', ('project/attributes/sshKeys',
                             'instance/attributes/sshKeys'), False, True),
            ('user-data', ('instance/attributes/user-data',), False, False),
            ('user-data-encoding', ('instance/attributes/user-data-encoding',),
             False, True),
        ]

        # if we cannot resolve the metadata server, then no point in trying
        if not util.is_resolvable_url(self.metadata_address):
            LOG.debug("%s is not resolvable", self.metadata_address)
            return False

        metadata_fetcher = GoogleMetadataFetcher(self.metadata_address)
        # iterate over url_map keys to get metadata items
        running_on_gce = False
        for (mkey, paths, required, is_text) in url_map:
            value = None
            for path in paths:
                new_value = metadata_fetcher.get_value(path, is_text)
                if new_value is not None:
                    value = new_value
            if value:
                running_on_gce = True
            if required and value is None:
                msg = "required key %s returned nothing. not GCE"
                if not running_on_gce:
                    LOG.debug(msg, mkey)
                else:
                    LOG.warn(msg, mkey)
                return False
            self.metadata[mkey] = value

        if self.metadata['public-keys']:
            lines = self.metadata['public-keys'].splitlines()
            self.metadata['public-keys'] = [self._trim_key(k) for k in lines]

        if self.metadata['availability-zone']:
            self.metadata['availability-zone'] = self.metadata[
                'availability-zone'].split('/')[-1]

        encoding = self.metadata.get('user-data-encoding')
        if encoding:
            if encoding == 'base64':
                self.metadata['user-data'] = b64decode(
                    self.metadata['user-data'])
            else:
                LOG.warn('unknown user-data-encoding: %s, ignoring', encoding)

        return running_on_gce

    @property
    def launch_index(self):
        # GCE does not provide lauch_index property
        return None

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_public_ssh_keys(self):
        return self.metadata['public-keys']

    def get_hostname(self, fqdn=False, resolve_ip=False):
        # GCE has long FDQN's and has asked for short hostnames
        return self.metadata['local-hostname'].split('.')[0]

    def get_userdata_raw(self):
        return self.metadata['user-data']

    @property
    def availability_zone(self):
        return self.metadata['availability-zone']

    @property
    def region(self):
        return self.availability_zone.rsplit('-', 1)[0]


# Used to match classes to dependencies
datasources = [
    (DataSourceGCE, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
