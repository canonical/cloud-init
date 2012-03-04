# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
#    Author: Cosmin Luta <cosmin.luta@avira.com>
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
import socket
import urllib2
import time
import boto.utils as boto_utils
from struct import pack

class DataSourceCS(DataSource.DataSource):
    api_ver = 'latest'
    seeddir = base_seeddir + '/cs'
    metadata_address = None

    def __init__(self, sys_cfg=None):
        DataSource.DataSource.__init__(self, sys_cfg)
        # Cloudstack has its metadata/userdata URLs located on http://<default-gateway-ip>/latest/
        self.metadata_address = "http://" + self._get_default_gateway() + "/"
        
    def _get_default_gateway(self):
        f = None
        try:
            f = open("/proc/net/route", "r")
            for line in f.readlines():
                items = line.split("\t")
                if items[1] == "00000000":
                    # found the default route, get the gateway
                    gw = int(items[2], 16)
                    log.debug("found default route, gateway %s" % items[2])
                    return socket.inet_ntoa(pack("<L", gw))
            f.close()
        except:
            if f is not None:
                f.close()
            return "localhost"

    def __str__(self):
        return "DataSourceCS"

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
            log.debug("crawl of metadata service took %ds" % (time.time() -
                                                              start))
            return True
        except Exception as e:
            log.exception(e)
            return False

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_availability_zone(self):
        return self.metadata['availability-zone']

datasources = [
  (DataSourceCS, (DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK)),
]

# return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return DataSource.list_from_depends(depends, datasources)
