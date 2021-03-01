# Author: Eric Benner <ebenner@vultr.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Vultr Metadata API:
# https://www.vultr.com/metadata/

import json
import re

from cloudinit import log as log
from cloudinit import sources
from cloudinit import util

import cloudinit.sources.helpers.vultr as vultr

LOGGER = log.getLogger(__name__)
BUILTIN_DS_CONFIG = {
    'url': 'http://169.254.169.254',
    'retries': 30,
    'timeout': 2,
    'wait': 2
}
CONFIG = BUILTIN_DS_CONFIG.copy()


class DataSourceVultr(sources.DataSource):

    dsname = 'Vultr'

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceVultr, self).__init__(sys_cfg, distro, paths)
        self.ds_cfg = util.mergemanydict([
            util.get_cfg_by_path(sys_cfg, ["datasource", "Vultr"], {}),
            BUILTIN_DS_CONFIG])
        CONFIG['url'] = self.ds_cfg.get(
            'url', BUILTIN_DS_CONFIG['url'])
        CONFIG['retries'] = self.ds_cfg.get(
            'retries', BUILTIN_DS_CONFIG['retries'])
        CONFIG['timeout'] = self.ds_cfg.get(
            'timeout', BUILTIN_DS_CONFIG['timeout'])
        CONFIG['wait'] = self.ds_cfg.get(
            'wait', BUILTIN_DS_CONFIG['wait'])

    # Initiate data and check if Vultr
    def _get_data(self):
        LOGGER.info("Detecting if machine is a Vultr instance")
        if not vultr.is_vultr():
            LOGGER.info("Machine is not a Vultr instance")
            return False

        LOGGER.info("Machine is a Vultr instance")

        config = vultr.generate_config(CONFIG)

        # Dump vendor config so diagnosing failures is manageable
        LOGGER.info("Vultr Vendor Config:")
        LOGGER.info(json.dumps(config))

        md = self.get_metadata()

        self.metadata_full = md
        self.metadata['instanceid'] = self.metadata_full['instanceid']
        self.metadata['local-hostname'] = re.sub(
            r'\W+', '', self.metadata_full['hostname'])

        # Default hostname is "vultr"
        if self.metadata['local-hostname'] == "":
            self.metadata['local-hostname'] = "vultr"

        self.metadata['public-keys'] = md["public-keys"].splitlines()
        self.userdata_raw = md["user-data"]
        if self.userdata_raw == "":
            self.userdata_raw = None
        self.vendordata_raw = "#cloud-config\n%s" % json.dumps(config)

        # Dump some data so diagnosing failures is manageable
        LOGGER.info("SUBID: %s", self.metadata['instanceid'])
        LOGGER.info("Hostname: %s", self.metadata['local-hostname'])
        if self.userdata_raw is not None:
            LOGGER.info("User-Data:")
            LOGGER.info(self.userdata_raw)

        return True

    # Get the metadata by flag
    def get_metadata(self):
        return vultr.get_metadata(CONFIG)

    # Currently unsupported
    @property
    def launch_index(self):
        return None

    # Write the base configs every time. These are subject to change
    @property
    def network_config(self):
        config = vultr.generate_network_config(CONFIG)
        config_raw = json.dumps(config)

        # Dump network config so diagnosing failures is manageable
        LOGGER.info("Generated Network:")
        LOGGER.info(config_raw)

        return config


# Used to match classes to dependencies
datasources = [
    (DataSourceVultr, (sources.DEP_FILESYSTEM, )),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
