# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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

import os
import time

import boto.utils as boto_utils

from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util

LOG = logging.getLogger(__name__)

DEF_MD_URL = "http://169.254.169.254"

# Which version we are requesting of the ec2 metadata apis
DEF_MD_VERSION = '2009-04-04'

# Default metadata urls that will be used if none are provided
# They will be checked for 'resolveability' and some of the
# following may be discarded if they do not resolve
DEF_MD_URLS = [DEF_MD_URL, "http://instance-data:8773"]


class DataSourceEc2(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata_address = DEF_MD_URL
        self.seed_dir = os.path.join(paths.seed_dir, "ec2")
        self.api_ver = DEF_MD_VERSION

    def __str__(self):
        return util.obj_name(self)

    def get_data(self):
        seed_ret = {}
        if util.read_optional_seed(seed_ret, base=(self.seed_dir + "/")):
            self.userdata_raw = seed_ret['user-data']
            self.metadata = seed_ret['meta-data']
            LOG.debug("Using seeded ec2 data from %s", self.seed_dir)
            return True

        try:
            if not self.wait_for_metadata_service():
                return False
            start_time = time.time()
            self.userdata_raw = boto_utils.get_instance_userdata(self.api_ver,
                None, self.metadata_address)
            self.metadata = boto_utils.get_instance_metadata(self.api_ver,
                self.metadata_address)
            LOG.debug("Crawl of metadata service took %s seconds",
                       int(time.time() - start_time))
            return True
        except Exception:
            util.logexc(LOG, "Failed reading from metadata address %s",
                        self.metadata_address)
            return False

    def get_instance_id(self):
        return self.metadata['instance-id']

    def get_availability_zone(self):
        return self.metadata['placement']['availability-zone']

    def get_local_mirror(self):
        return self.get_mirror_from_availability_zone()

    def get_mirror_from_availability_zone(self, availability_zone=None):
        # Return type None indicates there is no cloud specific mirror
        # Availability is like 'us-west-1b' or 'eu-west-1a'
        if availability_zone is None:
            availability_zone = self.get_availability_zone()

        if self.is_vpc():
            return None

        if not availability_zone:
            return None

        mirror_tpl = self.distro.get_option('package_mirror_ec2_template',
                                             None)

        if mirror_tpl is None:
            return None

        # in EC2, the 'region' is 'us-east-1' if 'zone' is 'us-east-1a'
        tpl_params = {
            'zone': availability_zone.strip(),
            'region': availability_zone[:-1]
        }
        mirror_url = mirror_tpl % (tpl_params)

        found = util.search_for_mirror([mirror_url])
        if found is not None:
            return mirror_url

        return None

    def _get_url_settings(self):
        mcfg = self.ds_cfg
        if not mcfg:
            mcfg = {}
        max_wait = 120
        try:
            max_wait = int(mcfg.get("max_wait", max_wait))
        except Exception:
            util.logexc(LOG, "Failed to get max wait. using %s", max_wait)

        if max_wait == 0:
            return False

        timeout = 50
        try:
            timeout = int(mcfg.get("timeout", timeout))
        except Exception:
            util.logexc(LOG, "Failed to get timeout, using %s", timeout)

        return (max_wait, timeout)

    def wait_for_metadata_service(self):
        mcfg = self.ds_cfg
        if not mcfg:
            mcfg = {}

        (max_wait, timeout) = self._get_url_settings()

        # Remove addresses from the list that wont resolve.
        mdurls = mcfg.get("metadata_urls", DEF_MD_URLS)
        filtered = [x for x in mdurls if util.is_resolvable_url(x)]

        if set(filtered) != set(mdurls):
            LOG.debug("Removed the following from metadata urls: %s",
                      list((set(mdurls) - set(filtered))))

        if len(filtered):
            mdurls = filtered
        else:
            LOG.warn("Empty metadata url list! using default list")
            mdurls = DEF_MD_URLS

        urls = []
        url2base = {}
        for url in mdurls:
            cur = "%s/%s/meta-data/instance-id" % (url, self.api_ver)
            urls.append(cur)
            url2base[cur] = url

        start_time = time.time()
        url = uhelp.wait_for_url(urls=urls, max_wait=max_wait,
                                timeout=timeout, status_cb=LOG.warn)

        if url:
            LOG.debug("Using metadata source: '%s'", url2base[url])
        else:
            LOG.critical("Giving up on md from %s after %s seconds",
                            urls, int(time.time() - start_time))

        self.metadata_address = url2base.get(url)
        return bool(url)

    def _remap_device(self, short_name):
        # LP: #611137
        # the metadata service may believe that devices are named 'sda'
        # when the kernel named them 'vda' or 'xvda'
        # we want to return the correct value for what will actually
        # exist in this instance
        mappings = {"sd": ("vd", "xvd")}
        for (nfrom, tlist) in mappings.iteritems():
            if not short_name.startswith(nfrom):
                continue
            for nto in tlist:
                cand = "/dev/%s%s" % (nto, short_name[len(nfrom):])
                if os.path.exists(cand):
                    return cand
        return None

    def device_name_to_device(self, name):
        # Consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        if 'block-device-mapping' not in self.metadata:
            return None

        # Example:
        # 'block-device-mapping':
        # {'ami': '/dev/sda1',
        # 'ephemeral0': '/dev/sdb',
        # 'root': '/dev/sda1'}
        found = None
        bdm_items = self.metadata['block-device-mapping'].iteritems()
        for (entname, device) in bdm_items:
            if entname == name:
                found = device
                break
            # LP: #513842 mapping in Euca has 'ephemeral' not 'ephemeral0'
            if entname == "ephemeral" and name == "ephemeral0":
                found = device

        if found is None:
            LOG.debug("Unable to convert %s to a device", name)
            return None

        ofound = found
        if not found.startswith("/"):
            found = "/dev/%s" % found

        if os.path.exists(found):
            return found

        remapped = self._remap_device(os.path.basename(found))
        if remapped:
            LOG.debug("Remapped device name %s => %s", (found, remapped))
            return remapped

        # On t1.micro, ephemeral0 will appear in block-device-mapping from
        # metadata, but it will not exist on disk (and never will)
        # at this point, we've verified that the path did not exist
        # in the special case of 'ephemeral0' return None to avoid bogus
        # fstab entry (LP: #744019)
        if name == "ephemeral0":
            return None
        return ofound

    def is_vpc(self):
        # See: https://bugs.launchpad.net/ubuntu/+source/cloud-init/+bug/615545
        # Detect that the machine was launched in a VPC.
        # But I did notice that when in a VPC, meta-data
        # does not have public-ipv4 and public-hostname
        # listed as a possibility.
        ph = "public-hostname"
        p4 = "public-ipv4"
        if ((ph not in self.metadata or self.metadata[ph] == "") and
            (p4 not in self.metadata or self.metadata[p4] == "")):
            return True
        return False


# Used to match classes to dependencies
datasources = [
  (DataSourceEc2, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
