# Copyright (C) 2015-2016 Bigstep Cloud Ltd.
#
# Author: Alexandru Sirbu <alexandru.sirbu@bigstep.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import errno
import json
import os

from cloudinit import sources, url_helper, util


class DataSourceBigstep(sources.DataSource):

    dsname = "Bigstep"

    def __init__(self, sys_cfg, distro, paths):
        super().__init__(sys_cfg, distro, paths)
        self.metadata = {}
        self.vendordata_raw = ""
        self.userdata_raw = ""

    def _get_data(self, apply_filter=False) -> bool:
        url = self._get_url_from_file()
        if url is None:
            return False
        response = url_helper.readurl(url)
        decoded = json.loads(response.contents.decode())
        self.metadata = decoded["metadata"]
        self.vendordata_raw = decoded["vendordata_raw"]
        self.userdata_raw = decoded["userdata_raw"]
        return True

    def _get_subplatform(self) -> str:
        """Return the subplatform metadata source details."""
        return f"metadata ({self._get_url_from_file()})"

    def _get_url_from_file(self):
        url_file = os.path.join(
            self.paths.cloud_dir, "data", "seed", "bigstep", "url"
        )
        try:
            content = util.load_text_file(url_file)
        except IOError as e:
            # If the file doesn't exist, then the server probably isn't a
            # Bigstep instance; otherwise, another problem exists which needs
            # investigation
            if e.errno == errno.ENOENT:
                return None
            else:
                raise
        return content


# Used to match classes to dependencies
datasources = [
    (DataSourceBigstep, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
