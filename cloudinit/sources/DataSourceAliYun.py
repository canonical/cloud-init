# This file is part of cloud-init. See LICENSE file for license information.

import os

from cloudinit import sources
from cloudinit.sources import DataSourceEc2 as EC2

DEF_MD_VERSION = "2016-01-01"


class DataSourceAliYun(EC2.DataSourceEc2):
    metadata_urls = ["http://100.100.100.200"]

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceAliYun, self).__init__(sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, "AliYun")
        self.api_ver = DEF_MD_VERSION

    def get_hostname(self, fqdn=False, _resolve_ip=False):
        return self.metadata.get('hostname', 'localhost.localdomain')

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get('public-keys', {}))


def parse_public_keys(public_keys):
    keys = []
    for key_id, key_body in public_keys.items():
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
    (DataSourceAliYun, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
