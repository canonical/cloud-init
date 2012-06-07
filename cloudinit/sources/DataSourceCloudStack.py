# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Cosmin Luta
#
#    Author: Cosmin Luta <q4break@gmail.com>
#    Author: Scott Moser <scott.moser@canonical.com>
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

import cloudinit.DataSource as DataSource

from cloudinit import seeddir as base_seeddir
from cloudinit import log
import cloudinit.util as util
from socket import inet_ntoa
import time
import boto.utils as boto_utils
from struct import pack


class DataSourceCloudStack(DataSource.DataSource):
    api_ver = 'latest'
    seeddir = base_seeddir + '/cs'
    metadata_address = None

    def __init__(self, sys_cfg=None):
        DataSource.DataSource.__init__(self, sys_cfg)
        # Cloudstack has its metadata/userdata URLs located at
        # http://<default-gateway-ip>/latest/
        self.metadata_address = "http://%s/" % self.get_default_gateway()

    def get_default_gateway(self):
        """ Returns the default gateway ip address in the dotted format
        """
        with open("/proc/net/route", "r") as f:
            for line in f.readlines():
                items = line.split("\t")
                if items[1] == "00000000":
                    # found the default route, get the gateway
                    gw = inet_ntoa(pack("<L", int(items[2], 16)))
                    log.debug("found default route, gateway is %s" % gw)
                    return gw

    def __str__(self):
        return "DataSourceCloudStack"

    def get_data(self):
        seedret = {}
        if util.read_optional_seed(seedret, base=self.seeddir + "/"):
            self.userdata_raw = seedret['user-data']
            self.metadata = seedret['meta-data']
            log.debug("using seeded cs data in %s" % self.seeddir)
            return True

        try:
            start = time.time()
            self.userdata_raw = boto_utils.get_instance_userdata(self.api_ver,
                None, self.metadata_address)
            self.metadata = boto_utils.get_instance_metadata(self.api_ver,
                self.metadata_address)
            log.debug("crawl of metadata service took %ds" %
                (time.time() - start))
            return True
        except Exception as e:
            log.exception(e)
            return False

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_availability_zone(self):
        return self.metadata['availability-zone']

datasources = [
  (DataSourceCloudStack, (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
]


# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return DataSource.list_from_depends(depends, datasources)
