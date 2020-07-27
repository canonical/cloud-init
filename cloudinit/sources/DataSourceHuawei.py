# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import sources
from cloudinit.sources import DataSourceEc2 as EC2

HUAWEI_PRODUCT = "Huawei"


class DataSourceHuawei(EC2.DataSourceEc2):

    dsname = 'Huawei'
    metadata_urls = ['http://169.254.169.254']

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = '2007-01-19'
    extended_metadata_versions = []

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        return self.metadata.get('hostname', 'localhost.localdomain')

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get('public-keys', {}))

    def _get_cloud_name(self):
        return HUAWEI_PRODUCT


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
    (DataSourceHuawei, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
