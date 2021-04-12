# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Vultr Metadata API:
# https://www.vultr.com/metadata/

from cloudinit import log as log
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.vultr as vultr

LOG = log.getLogger(__name__)
BUILTIN_DS_CONFIG = {
    'url': 'http://169.254.169.254',
    'retries': 30,
    'timeout': 2,
    'wait': 2
}


class DataSourceVultr(sources.DataSource):

    dsname = 'Vultr'

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceVultr, self).__init__(sys_cfg, distro, paths)
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "Vultr"], {}),
            BUILTIN_DS_CONFIG])

    # Initiate data and check if Vultr
    def _get_data(self):
        LOG.debug("Detecting if machine is a Vultr instance")
        if not vultr.is_vultr():
            LOG.debug("Machine is not a Vultr instance")
            return False

        LOG.debug("Machine is a Vultr instance")

        # Fetch metadata
        md = self.get_metadata()

        self.metadata_full = md
        self.metadata['instanceid'] = md['instanceid']
        self.metadata['local-hostname'] = md['hostname']
        self.metadata['public-keys'] = md["public-keys"]
        self.userdata_raw = md["user-data"]

        # Generate config and process data
        self.get_datasource_data(md)

        # Dump some data so diagnosing failures is manageable
        LOG.debug("Vultr Vendor Config:")
        LOG.debug(md['vendor-data']['config'])
        LOG.debug("SUBID: %s", self.metadata['instanceid'])
        LOG.debug("Hostname: %s", self.metadata['local-hostname'])
        if self.userdata_raw is not None:
            LOG.debug("User-Data:")
            LOG.debug(self.userdata_raw)

        return True

    # Process metadata
    def get_datasource_data(self, md):
        # Grab config
        config = md['vendor-data']['config']

        # Generate network config
        self.netcfg = vultr.generate_network_config(md['interfaces'])

        # This requires info generated in the vendor config
        user_scripts = vultr.generate_user_scripts(md, self.netcfg['config'])

        # Default hostname is "guest" for whitelabel
        if self.metadata['local-hostname'] == "":
            self.metadata['local-hostname'] = "guest"

        self.userdata_raw = md["user-data"]
        if self.userdata_raw == "":
            self.userdata_raw = None

        # Assemble vendor-data
        # This adds provided scripts and the config
        self.vendordata_raw = []
        self.vendordata_raw.extend(user_scripts)
        self.vendordata_raw.append("#cloud-config\n%s" % config)

    # Get the metadata by flag
    def get_metadata(self):
        return vultr.get_metadata(self.ds_cfg['url'],
                                  self.ds_cfg['timeout'],
                                  self.ds_cfg['retries'],
                                  self.ds_cfg['wait'])

    # Compare subid as instance id
    def check_instance_id(self, sys_cfg):
        if not vultr.is_vultr():
            return False

        # Baremetal has no way to implement this in local
        if vultr.is_baremetal():
            return False

        subid = vultr.get_sysinfo()['subid']
        return sources.instance_id_matches_system_uuid(subid)

    # Currently unsupported
    @property
    def launch_index(self):
        return None

    @property
    def network_config(self):
        return self.netcfg


# Used to match classes to dependencies
datasources = [
    (DataSourceVultr, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


if __name__ == "__main__":
    import sys

    if not vultr.is_vultr():
        print("Machine is not a Vultr instance")
        sys.exit(1)

    md = vultr.get_metadata(BUILTIN_DS_CONFIG['url'],
                            BUILTIN_DS_CONFIG['timeout'],
                            BUILTIN_DS_CONFIG['retries'],
                            BUILTIN_DS_CONFIG['wait'])
    config = md['vendor-data']['config']
    sysinfo = vultr.get_sysinfo()

    print(util.json_dumps(sysinfo))
    print(config)

# vi: ts=4 expandtab
