# Author: Marques Johansson <mjohansson@equinix.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# EquinixMetal Metadata API:
# https://metal.equinix.com/developers/docs/servers/metadata/

import re

from cloudinit import log as logging
from cloudinit.sources import DataSourceEc2 as EC2
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.equinixmetal as equinixmetal_helper

LOG = logging.getLogger(__name__)

BUILTIN_DS_CONFIG = {
    'metadata_url': 'https://metadata.platformequinix.com/metadata',
    'userdata_url': 'https://metadata.platformequinix.com/userdata',
}


EQUINIXMETAL_IQN_PATTERN = "iqn\.[0-9-]{6,7}\.(net\.packet|equinix\.metal):"


class DataSourceEquinixMetal(EC2.DataSourceEc2):

    dsname = 'EquinixMetal'
    metadata_urls = ['https://metadata.platformequinix.com']

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = '2009-04-04'
    extended_metadata_versions = []

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        return self.metadata.get('hostname', 'localhost.localdomain')

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get('public-keys', {}))

    def _get_cloud_name(self):
        if _is_equinixmetal():
            return EC2.CloudNames.EQUINIXMETAL
        else:
            return EC2.CloudNames.NO_EC2_METADATA


def _is_equinixmetal():
    return re.match(EQUINIXMETAL_IQN_PATTERN, self.metadata.get('iqn', ''))


def parse_public_keys(public_keys):
    keys = []
    for _key_id, key_body in public_keys.items():
        if isinstance(key_body, str):
            keys.append(key_body.strip())
        elif isinstance(key_body, list):
            keys.extend(key_body)
        elif isinstance(key_body, dict):
            key = key_body.get('openssh-key', [])
            if isinstance(key, str):
                keys.append(key.strip())
            elif isinstance(key, list):
                keys.extend(key)
    return keys


# Used to match classes to dependencies
datasources = [
    (DataSourceEquinixMetal, (sources.DEP_NETWORK)),
]

# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
