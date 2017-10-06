# Author: Vaidas Jablonskis <jablonskis@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from base64 import b64decode

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper
from cloudinit import util

LOG = logging.getLogger(__name__)

MD_V1_URL = 'http://metadata.google.internal/computeMetadata/v1/'
BUILTIN_DS_CONFIG = {'metadata_url': MD_V1_URL}
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

    def get_data(self):
        ret = util.log_time(
            LOG.debug, 'Crawl of GCE metadata service',
            read_md, kwargs={'address': self.metadata_address})

        if not ret['success']:
            if ret['platform_reports_gce']:
                LOG.warning(ret['reason'])
            else:
                LOG.debug(ret['reason'])
            return False
        self.metadata = ret['meta-data']
        self.userdata_raw = ret['user-data']
        return True

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

    @property
    def availability_zone(self):
        return self.metadata['availability-zone']

    @property
    def region(self):
        return self.availability_zone.rsplit('-', 1)[0]


def _trim_key(public_key):
    # GCE takes sshKeys attribute in the format of '<user>:<public_key>'
    # so we have to trim each key to remove the username part
    try:
        index = public_key.index(':')
        if index > 0:
            return public_key[(index + 1):]
    except Exception:
        return public_key


def read_md(address=None, platform_check=True):

    if address is None:
        address = MD_V1_URL

    ret = {'meta-data': None, 'user-data': None,
           'success': False, 'reason': None}
    ret['platform_reports_gce'] = platform_reports_gce()

    if platform_check and not ret['platform_reports_gce']:
        ret['reason'] = "Not running on GCE."
        return ret

    # if we cannot resolve the metadata server, then no point in trying
    if not util.is_resolvable_url(address):
        LOG.debug("%s is not resolvable", address)
        ret['reason'] = 'address "%s" is not resolvable' % address
        return ret

    # url_map: (our-key, path, required, is_text)
    url_map = [
        ('instance-id', ('instance/id',), True, True),
        ('availability-zone', ('instance/zone',), True, True),
        ('local-hostname', ('instance/hostname',), True, True),
        ('public-keys', ('project/attributes/sshKeys',
                         'instance/attributes/ssh-keys'), False, True),
        ('user-data', ('instance/attributes/user-data',), False, False),
        ('user-data-encoding', ('instance/attributes/user-data-encoding',),
         False, True),
    ]

    metadata_fetcher = GoogleMetadataFetcher(address)
    md = {}
    # iterate over url_map keys to get metadata items
    for (mkey, paths, required, is_text) in url_map:
        value = None
        for path in paths:
            new_value = metadata_fetcher.get_value(path, is_text)
            if new_value is not None:
                value = new_value
        if required and value is None:
            msg = "required key %s returned nothing. not GCE"
            ret['reason'] = msg % mkey
            return ret
        md[mkey] = value

    if md['public-keys']:
        lines = md['public-keys'].splitlines()
        md['public-keys'] = [_trim_key(k) for k in lines]

    if md['availability-zone']:
        md['availability-zone'] = md['availability-zone'].split('/')[-1]

    encoding = md.get('user-data-encoding')
    if encoding:
        if encoding == 'base64':
            md['user-data'] = b64decode(md['user-data'])
        else:
            LOG.warning('unknown user-data-encoding: %s, ignoring', encoding)

    if 'user-data' in md:
        ret['user-data'] = md['user-data']
        del md['user-data']

    ret['meta-data'] = md
    ret['success'] = True

    return ret


def platform_reports_gce():
    pname = util.read_dmi_data('system-product-name') or "N/A"
    if pname == "Google Compute Engine":
        return True

    # system-product-name is not always guaranteed (LP: #1674861)
    serial = util.read_dmi_data('system-serial-number') or "N/A"
    if serial.startswith("GoogleCloud-"):
        return True

    LOG.debug("Not running on google cloud. product-name=%s serial=%s",
              pname, serial)
    return False


# Used to match classes to dependencies
datasources = [
    (DataSourceGCE, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    from base64 import b64encode

    parser = argparse.ArgumentParser(description='Query GCE Metadata Service')
    parser.add_argument("--endpoint", metavar="URL",
                        help="The url of the metadata service.",
                        default=MD_V1_URL)
    parser.add_argument("--no-platform-check", dest="platform_check",
                        help="Ignore smbios platform check",
                        action='store_false', default=True)
    args = parser.parse_args()
    data = read_md(address=args.endpoint, platform_check=args.platform_check)
    if 'user-data' in data:
        # user-data is bytes not string like other things. Handle it specially.
        # if it can be represented as utf-8 then do so.  Otherwise print base64
        # encoded value in the key user-data-b64.
        try:
            data['user-data'] = data['user-data'].decode()
        except UnicodeDecodeError:
            sys.stderr.write("User-data cannot be decoded. "
                             "Writing as base64\n")
            del data['user-data']
            # b64encode returns a bytes value. decode to get the string.
            data['user-data-b64'] = b64encode(data['user-data']).decode()

    print(json.dumps(data, indent=1, sort_keys=True, separators=(',', ': ')))

# vi: ts=4 expandtab
