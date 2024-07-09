# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import sources


class DataSourceNone(sources.DataSource):

    dsname = "None"

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        sources.DataSource.__init__(self, sys_cfg, distro, paths, ud_proc)
        self.metadata = {}
        self.userdata_raw = ""

    def _get_data(self):
        # If the datasource config has any provided 'fallback'
        # userdata or metadata, use it...
        if "userdata_raw" in self.ds_cfg:
            self.userdata_raw = self.ds_cfg["userdata_raw"]
        if "metadata" in self.ds_cfg:
            self.metadata = self.ds_cfg["metadata"]
        return True

    def _get_subplatform(self):
        """Return the subplatform metadata source details."""
        return "config"

    def get_instance_id(self):
        return "iid-datasource-none"


# Used to match classes to dependencies
datasources = [
    (DataSourceNone, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
    (DataSourceNone, []),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
