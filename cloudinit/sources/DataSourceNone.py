# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
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
from cloudinit import sources

LOG = logging.getLogger(__name__)


class DataSourceNone(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        sources.DataSource.__init__(self, sys_cfg, distro, paths, ud_proc)
        self.metadata = {}
        self.userdata_raw = ''

    def get_data(self):
        # If the datasource config has any provided 'fallback'
        # userdata or metadata, use it...
        if 'userdata_raw' in self.ds_cfg:
            self.userdata_raw = self.ds_cfg['userdata_raw']
        if 'metadata' in self.ds_cfg:
            self.metadata = self.ds_cfg['metadata']
        return True

    def get_instance_id(self):
        return 'iid-datasource-none'

    @property
    def is_disconnected(self):
        return True


# Used to match classes to dependencies
datasources = [
  (DataSourceNone, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
  (DataSourceNone, []),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
