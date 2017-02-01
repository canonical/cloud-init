# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Cosmin Luta
# Copyright (C) 2012 Yahoo! Inc.
# Copyright (C) 2012 Gerard Dethier
# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Cosmin Luta <q4break@gmail.com>
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
# Author: Gerard Dethier <g.dethier@gmail.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
from socket import inet_ntoa
from struct import pack
import time

from cloudinit import ec2_utils as ec2
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util

LOG = logging.getLogger(__name__)


class CloudStackPasswordServerClient(object):
    """
    Implements password fetching from the CloudStack password server.

    http://cloudstack-administration.readthedocs.org/
       en/latest/templates.html#adding-password-management-to-your-templates
    has documentation about the system.  This implementation is following that
    found at
    https://github.com/shankerbalan/cloudstack-scripts/
       blob/master/cloud-set-guest-password-debian
    """

    def __init__(self, virtual_router_address):
        self.virtual_router_address = virtual_router_address

    def _do_request(self, domu_request):
        # The password server was in the past, a broken HTTP server, but is now
        # fixed.  wget handles this seamlessly, so it's easier to shell out to
        # that rather than write our own handling code.
        output, _ = util.subp([
            'wget', '--quiet', '--tries', '3', '--timeout', '20',
            '--output-document', '-', '--header',
            'DomU_Request: {0}'.format(domu_request),
            '{0}:8080'.format(self.virtual_router_address)
        ])
        return output.strip()

    def get_password(self):
        password = self._do_request('send_my_password')
        if password in ['', 'saved_password']:
            return None
        if password == 'bad_request':
            raise RuntimeError('Error when attempting to fetch root password.')
        self._do_request('saved_password')
        return password


class DataSourceCloudStack(sources.DataSource):
    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, 'cs')
        # Cloudstack has its metadata/userdata URLs located at
        # http://<virtual-router-ip>/latest/
        self.api_ver = 'latest'
        self.vr_addr = get_vr_address()
        if not self.vr_addr:
            raise RuntimeError("No virtual router found!")
        self.metadata_address = "http://%s/" % (self.vr_addr,)
        self.cfg = {}

    def _get_url_settings(self):
        mcfg = self.ds_cfg
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
        (max_wait, timeout) = self._get_url_settings()

        urls = [uhelp.combine_url(self.metadata_address,
                                  'latest/meta-data/instance-id')]
        start_time = time.time()
        url = uhelp.wait_for_url(urls=urls, max_wait=max_wait,
                                 timeout=timeout, status_cb=LOG.warn)

        if url:
            LOG.debug("Using metadata source: '%s'", url)
        else:
            LOG.critical(("Giving up on waiting for the metadata from %s"
                          " after %s seconds"),
                         urls, int(time.time() - start_time))

        return bool(url)

    def get_config_obj(self):
        return self.cfg

    def get_data(self):
        seed_ret = {}
        if util.read_optional_seed(seed_ret, base=(self.seed_dir + "/")):
            self.userdata_raw = seed_ret['user-data']
            self.metadata = seed_ret['meta-data']
            LOG.debug("Using seeded cloudstack data from: %s", self.seed_dir)
            return True
        try:
            if not self.wait_for_metadata_service():
                return False
            start_time = time.time()
            self.userdata_raw = ec2.get_instance_userdata(
                self.api_ver, self.metadata_address)
            self.metadata = ec2.get_instance_metadata(self.api_ver,
                                                      self.metadata_address)
            LOG.debug("Crawl of metadata service took %s seconds",
                      int(time.time() - start_time))
            password_client = CloudStackPasswordServerClient(self.vr_addr)
            try:
                set_password = password_client.get_password()
            except Exception:
                util.logexc(LOG,
                            'Failed to fetch password from virtual router %s',
                            self.vr_addr)
            else:
                if set_password:
                    self.cfg = {
                        'ssh_pwauth': True,
                        'password': set_password,
                        'chpasswd': {
                            'expire': False,
                        },
                    }
            return True
        except Exception:
            util.logexc(LOG, 'Failed fetching from metadata service %s',
                        self.metadata_address)
            return False

    def get_instance_id(self):
        return self.metadata['instance-id']

    @property
    def availability_zone(self):
        return self.metadata['availability-zone']


def get_default_gateway():
    # Returns the default gateway ip address in the dotted format.
    lines = util.load_file("/proc/net/route").splitlines()
    for line in lines:
        items = line.split("\t")
        if items[1] == "00000000":
            # Found the default route, get the gateway
            gw = inet_ntoa(pack("<L", int(items[2], 16)))
            LOG.debug("Found default route, gateway is %s", gw)
            return gw
    return None


def get_dhclient_d():
    # find lease files directory
    supported_dirs = ["/var/lib/dhclient", "/var/lib/dhcp"]
    for d in supported_dirs:
        if os.path.exists(d):
            LOG.debug("Using %s lease directory", d)
            return d
    return None


def get_latest_lease():
    # find latest lease file
    lease_d = get_dhclient_d()
    if not lease_d:
        return None
    lease_files = os.listdir(lease_d)
    latest_mtime = -1
    latest_file = None
    for file_name in lease_files:
        if file_name.startswith("dhclient.") and \
           (file_name.endswith(".lease") or file_name.endswith(".leases")):
            abs_path = os.path.join(lease_d, file_name)
            mtime = os.path.getmtime(abs_path)
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = abs_path
    return latest_file


def get_vr_address():
    # Get the address of the virtual router via dhcp leases
    # see http://bit.ly/T76eKC for documentation on the virtual router.
    # If no virtual router is detected, fallback on default gateway.
    lease_file = get_latest_lease()
    if not lease_file:
        LOG.debug("No lease file found, using default gateway")
        return get_default_gateway()

    latest_address = None
    with open(lease_file, "r") as fd:
        for line in fd:
            if "dhcp-server-identifier" in line:
                words = line.strip(" ;\r\n").split(" ")
                if len(words) > 2:
                    dhcp = words[2]
                    LOG.debug("Found DHCP identifier %s", dhcp)
                    latest_address = dhcp
    if not latest_address:
        # No virtual router found, fallback on default gateway
        LOG.debug("No DHCP found, using default gateway")
        return get_default_gateway()
    return latest_address


# Used to match classes to dependencies
datasources = [
    (DataSourceCloudStack, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
