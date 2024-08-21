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

import logging
import os
import time
from contextlib import suppress
from socket import gaierror, getaddrinfo, inet_ntoa
from struct import pack

from cloudinit import sources, subp
from cloudinit import url_helper as uhelp
from cloudinit import util
from cloudinit.net import dhcp
from cloudinit.sources.helpers import ec2

LOG = logging.getLogger(__name__)


class CloudStackPasswordServerClient:
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
        output, _ = subp.subp(
            [
                "wget",
                "--quiet",
                "--tries",
                "3",
                "--timeout",
                "20",
                "--output-document",
                "-",
                "--header",
                "DomU_Request: {0}".format(domu_request),
                "{0}:8080".format(self.virtual_router_address),
            ]
        )
        return output.strip()

    def get_password(self):
        password = self._do_request("send_my_password")
        if password in ["", "saved_password"]:
            return None
        if password == "bad_request":
            raise RuntimeError("Error when attempting to fetch root password.")
        self._do_request("saved_password")
        return password


class DataSourceCloudStack(sources.DataSource):

    dsname = "CloudStack"

    # Setup read_url parameters per get_url_params.
    url_max_wait = 120
    url_timeout = 50

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.seed_dir = os.path.join(paths.seed_dir, "cs")
        # Cloudstack has its metadata/userdata URLs located at
        # http://<virtual-router-ip>/latest/
        self.api_ver = "latest"

        self.distro = distro
        self.vr_addr = get_vr_address(self.distro)
        if not self.vr_addr:
            raise RuntimeError("No virtual router found!")
        self.metadata_address = f"http://{self.vr_addr}/"
        self.cfg = {}

    def _get_domainname(self):
        """
        Try obtaining a "domain-name" DHCP lease parameter:
        - From systemd-networkd lease
        - From dhclient lease
        """
        LOG.debug("Try obtaining domain name from networkd leases")
        domainname = dhcp.networkd_get_option_from_leases("DOMAINNAME")
        if domainname:
            return domainname
        LOG.debug(
            "Could not obtain FQDN from networkd leases. "
            "Falling back to ISC dhclient"
        )

        # some distros might use isc-dhclient for network setup via their
        # network manager. If this happens, the lease is more recent than the
        # ephemeral lease, so use it first.
        with suppress(dhcp.NoDHCPLeaseMissingDhclientError):
            domain_name = dhcp.IscDhclient().get_key_from_latest_lease(
                self.distro, "domain-name"
            )
            if domain_name:
                return domain_name

        LOG.debug(
            "Could not obtain FQDN from ISC dhclient leases. "
            "Falling back to %s",
            self.distro.dhcp_client.client_name,
        )

        # If no distro leases were found, check the ephemeral lease that
        # cloud-init set up.
        with suppress(FileNotFoundError):
            latest_lease = self.distro.dhcp_client.get_newest_lease(
                self.distro.fallback_interface
            )
            domain_name = latest_lease.get("domain-name") or None
            return domain_name
        LOG.debug("No dhcp leases found")
        return None

    def get_hostname(
        self,
        fqdn=False,
        resolve_ip=False,
        metadata_only=False,
    ):
        """
        Returns instance's hostname / fqdn
        First probes the parent class method.

        If fqdn is requested, and the parent method didn't return it,
        then attach the domain-name from DHCP response.
        """
        hostname = super().get_hostname(fqdn, resolve_ip, metadata_only)
        if fqdn and "." not in hostname.hostname:
            LOG.debug("FQDN requested")
            domainname = self._get_domainname()
            if domainname:
                fqdn = f"{hostname.hostname}.{domainname}"
                LOG.debug("Obtained the following FQDN: %s", fqdn)
                return sources.DataSourceHostname(fqdn, hostname.is_default)
            LOG.debug(
                "Could not determine domain name for FQDN. "
                "Fall back to hostname as an FQDN: %s",
                fqdn,
            )
        return hostname

    def wait_for_metadata_service(self):
        url_params = self.get_url_params()

        if url_params.max_wait_seconds <= 0:
            return False

        urls = [
            uhelp.combine_url(
                self.metadata_address, "latest/meta-data/instance-id"
            )
        ]
        start_time = time.monotonic()
        url, _response = uhelp.wait_for_url(
            urls=urls,
            max_wait=url_params.max_wait_seconds,
            timeout=url_params.timeout_seconds,
            status_cb=LOG.warning,
        )

        if url:
            LOG.debug("Using metadata source: '%s'", url)
        else:
            LOG.critical(
                "Giving up on waiting for the metadata from %s"
                " after %s seconds",
                urls,
                int(time.monotonic() - start_time),
            )

        return bool(url)

    def get_config_obj(self):
        return self.cfg

    def _get_data(self):
        seed_ret = {}
        if util.read_optional_seed(seed_ret, base=(self.seed_dir + "/")):
            self.userdata_raw = seed_ret["user-data"]
            self.metadata = seed_ret["meta-data"]
            LOG.debug("Using seeded cloudstack data from: %s", self.seed_dir)
            return True
        try:
            if not self.wait_for_metadata_service():
                return False
            start_time = time.monotonic()
            self.userdata_raw = ec2.get_instance_userdata(
                self.api_ver, self.metadata_address
            )
            self.metadata = ec2.get_instance_metadata(
                self.api_ver, self.metadata_address
            )
            LOG.debug(
                "Crawl of metadata service took %s seconds",
                int(time.monotonic() - start_time),
            )
            password_client = CloudStackPasswordServerClient(self.vr_addr)
            try:
                set_password = password_client.get_password()
            except Exception:
                util.logexc(
                    LOG,
                    "Failed to fetch password from virtual router %s",
                    self.vr_addr,
                )
            else:
                if set_password:
                    self.cfg = {
                        "ssh_pwauth": True,
                        "password": set_password,
                        "chpasswd": {
                            "expire": False,
                        },
                    }
            return True
        except Exception:
            util.logexc(
                LOG,
                "Failed fetching from metadata service %s",
                self.metadata_address,
            )
            return False

    def get_instance_id(self):
        return self.metadata["instance-id"]

    @property
    def availability_zone(self):
        return self.metadata["availability-zone"]


def get_data_server():
    # Returns the metadataserver from dns
    try:
        addrinfo = getaddrinfo("data-server", 80)
    except gaierror:
        LOG.debug("DNS Entry data-server not found")
        return None
    else:
        return addrinfo[0][4][0]  # return IP


def get_default_gateway():
    # Returns the default gateway ip address in the dotted format.
    lines = util.load_text_file("/proc/net/route").splitlines()
    for line in lines:
        items = line.split("\t")
        if items[1] == "00000000":
            # Found the default route, get the gateway
            gw = inet_ntoa(pack("<L", int(items[2], 16)))
            LOG.debug("Found default route, gateway is %s", gw)
            return gw
    return None


def get_vr_address(distro):
    # Get the address of the virtual router via dhcp leases
    # If no virtual router is detected, fallback on default gateway.
    # See http://docs.cloudstack.apache.org/projects/cloudstack-administration/en/4.8/virtual_machines/user-data.html # noqa

    # Try data-server DNS entry first
    latest_address = get_data_server()
    if latest_address:
        LOG.debug(
            "Found metadata server '%s' via data-server DNS entry",
            latest_address,
        )
        return latest_address

    # Try networkd second...
    latest_address = dhcp.networkd_get_option_from_leases("SERVER_ADDRESS")
    if latest_address:
        LOG.debug(
            "Found SERVER_ADDRESS '%s' via networkd_leases", latest_address
        )
        return latest_address

    # Try dhcp lease files next
    # get_key_from_latest_lease() needs a Distro object to know which directory
    # stores lease files
    with suppress(dhcp.NoDHCPLeaseMissingDhclientError):
        latest_address = dhcp.IscDhclient().get_key_from_latest_lease(
            distro, "dhcp-server-identifier"
        )
        if latest_address:
            LOG.debug("Found SERVER_ADDRESS '%s' via dhclient", latest_address)
            return latest_address

    with suppress(FileNotFoundError):
        latest_lease = distro.dhcp_client.get_newest_lease(distro)
        if latest_lease:
            LOG.debug(
                "Found SERVER_ADDRESS '%s' via ephemeral %s lease ",
                latest_lease,
                distro.dhcp_client.client_name,
            )
            return latest_lease

    # No virtual router found, fallback to default gateway
    LOG.debug("No DHCP found, using default gateway")
    return get_default_gateway()


# Used to match classes to dependencies
datasources = [
    (DataSourceCloudStack, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
