# Author: Julien Castets <castets.j@gmail.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

# Scaleway API:
# https://developer.scaleway.com/#metadata

import json
import logging
import os
import socket
import time
from urllib.parse import urlparse

import requests
from requests.exceptions import ConnectionError

# Note: `urllib3` is transitively installed by `requests`
from urllib3.connection import HTTPConnection
from urllib3.poolmanager import PoolManager

from cloudinit import dmi, sources, url_helper, util
from cloudinit.event import EventScope, EventType
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4, EphemeralIPv6Network
from cloudinit.sources import DataSourceHostname
from cloudinit.subp import ProcessExecutionError

LOG = logging.getLogger(__name__)

DS_BASE_URLS = ["http://169.254.42.42", "http://[fd00:42::42]"]

DEF_MD_RETRIES = 3
DEF_MD_MAX_WAIT = 2
DEF_MD_TIMEOUT = 10


class SourceAddressAdapter(requests.adapters.HTTPAdapter):
    """
    Adapter for requests to choose the local address to bind to.
    """

    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super(SourceAddressAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        socket_options = HTTPConnection.default_socket_options + [
            (socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        ]
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            source_address=self.source_address,
            socket_options=socket_options,
        )


def query_data_api_once(api_address, timeout, requests_session):
    """
    Retrieve user data or vendor data.

    Scaleway user/vendor data API returns HTTP/404 if user/vendor data is not
    set.

    This function calls `url_helper.readurl` but instead of considering
    HTTP/404 as an error that requires a retry, it considers it as empty
    user/vendor data.

    Also, be aware the user data/vendor API requires the source port to be
    below 1024 to ensure the client is root (since non-root users can't bind
    ports below 1024). If requests raises ConnectionError (EADDRINUSE), the
    caller should retry to call this function on an other port.
    """
    try:
        resp = url_helper.readurl(
            api_address,
            data=None,
            timeout=timeout,
            # It's the caller's responsibility to recall this function in case
            # of exception. Don't let url_helper.readurl() retry by itself.
            retries=0,
            session=requests_session,
            # If the error is a HTTP/404 or a ConnectionError, go into raise
            # block below and don't bother retrying.
            exception_cb=lambda _, exc: exc.code != 404
            and (
                not isinstance(exc.cause, requests.exceptions.ConnectionError)
            ),
        )
        return util.decode_binary(resp.contents)
    except url_helper.UrlError as exc:
        # Empty user data.
        if exc.code == 404:
            return None
        raise


def query_data_api(api_type, api_address, retries, timeout):
    """Get user or vendor data.

    Handle the retrying logic in case the source port is used.

    Scaleway metadata service requires the source port of the client to
    be a privileged port (<1024).  This is done to ensure that only a
    privileged user on the system can access the metadata service.
    """
    # Query user/vendor data. Try to make a request on the first privileged
    # port available.
    for port in range(1, max(retries, 2)):
        try:
            LOG.debug(
                "Trying to get %s data (bind on port %d)...", api_type, port
            )
            requests_session = requests.Session()
            # Adapt Session.mount to IPv4/IPv6 context
            localhost = "0.0.0.0"
            try:
                url_address = urlparse(api_address).netloc
                address = url_address
                if url_address[0] == "[":
                    address = url_address[1:-1]
                addr_proto = socket.getaddrinfo(
                    address, None, proto=socket.IPPROTO_TCP
                )[0][0]
                if addr_proto == socket.AF_INET6:
                    localhost = "0::"
            except ValueError:
                pass
            requests_session.mount(
                "http://",
                SourceAddressAdapter(source_address=(localhost, port)),
            )
            data = query_data_api_once(
                api_address, timeout=timeout, requests_session=requests_session
            )
            LOG.debug("%s-data downloaded", api_type)
            return data

        except url_helper.UrlError as exc:
            # Local port already in use or HTTP/429.
            LOG.warning("Error while trying to get %s data: %s", api_type, exc)
            time.sleep(5)
            last_exc = exc
            continue

    # Max number of retries reached.
    raise last_exc


class DataSourceScaleway(sources.DataSource):
    dsname = "Scaleway"
    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
        }
    }

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceScaleway, self).__init__(sys_cfg, distro, paths)

        self.ds_cfg = util.mergemanydict(
            [
                util.get_cfg_by_path(sys_cfg, ["datasource", "Scaleway"], {}),
            ]
        )

        self.retries = int(self.ds_cfg.get("retries", DEF_MD_RETRIES))
        self.timeout = int(self.ds_cfg.get("timeout", DEF_MD_TIMEOUT))
        self.max_wait = int(self.ds_cfg.get("max_wait", DEF_MD_MAX_WAIT))
        self._network_config = sources.UNSET
        self.metadata_urls = DS_BASE_URLS
        self.metadata_url = None
        self.userdata_url = None
        self.vendordata_url = None
        self.ephemeral_fixed_address = None
        self.has_ipv4 = True
        if "metadata_urls" in self.ds_cfg.keys():
            self.metadata_urls += self.ds_cfg["metadata_urls"]

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        attr_defaults = {
            "ephemeral_fixed_address": None,
            "has_ipv4": True,
            "max_wait": DEF_MD_MAX_WAIT,
            "metadata_urls": DS_BASE_URLS,
            "userdata_url": None,
            "vendordata_url": None,
        }
        for attr in attr_defaults:
            if not hasattr(self, attr):
                setattr(self, attr, attr_defaults[attr])

    def _set_metadata_url(self, urls):
        """
        Define metadata_url based upon api-metadata URL availability.
        """

        start_time = time.monotonic()
        avail_url, _ = url_helper.wait_for_url(
            urls=urls,
            max_wait=self.max_wait,
            timeout=self.timeout,
            connect_synchronously=False,
        )
        if avail_url:
            LOG.debug("%s is reachable", avail_url)
            self.metadata_url = f"{avail_url}/conf?format=json"
            self.userdata_url = f"{avail_url}/user_data/cloud-init"
            self.vendordata_url = f"{avail_url}/vendor_data/cloud-init"
            return
        else:
            LOG.debug(
                "Unable to reach api-metadata at %s after %s seconds",
                urls,
                int(time.monotonic() - start_time),
            )
            raise ConnectionError

    def _crawl_metadata(self):
        resp = url_helper.readurl(
            self.metadata_url, timeout=self.timeout, retries=self.retries
        )
        self.metadata = json.loads(util.decode_binary(resp.contents))

        self.userdata_raw = query_data_api(
            "user-data", self.userdata_url, self.retries, self.timeout
        )
        self.vendordata_raw = query_data_api(
            "vendor-data", self.vendordata_url, self.retries, self.timeout
        )

    @staticmethod
    def ds_detect():
        """
        There are three ways to detect if you are on Scaleway:

        * check DMI data: not yet implemented by Scaleway, but the check is
          made to be future-proof.
        * the initrd created the file /var/run/scaleway.
        * "scaleway" is in the kernel cmdline.
        """
        vendor_name = dmi.read_dmi_data("system-manufacturer")
        if vendor_name == "Scaleway":
            return True

        if os.path.exists("/var/run/scaleway"):
            return True

        cmdline = util.get_cmdline()
        if "scaleway" in cmdline:
            return True

    def _set_urls_on_ip_version(self, proto, urls):

        if proto not in ["ipv4", "ipv6"]:
            LOG.debug("Invalid IP version : %s", proto)
            return []

        filtered_urls = []
        for url in urls:
            # Numeric IPs
            address = urlparse(url).netloc
            if address[0] == "[":
                address = address[1:-1]
            addr_proto = socket.getaddrinfo(
                address, None, proto=socket.IPPROTO_TCP
            )[0][0]
            if addr_proto == socket.AF_INET and proto == "ipv4":
                filtered_urls += [url]
                continue
            elif addr_proto == socket.AF_INET6 and proto == "ipv6":
                filtered_urls += [url]
                continue

        return filtered_urls

    def _get_data(self):

        # The DataSource uses EventType.BOOT so we are called more than once.
        # Try to crawl metadata on IPv4 first and set has_ipv4 to False if we
        # timeout so we do not try to crawl on IPv4 more than once.
        if self.has_ipv4:
            try:
                # DHCPv4 waits for timeout defined in /etc/dhcp/dhclient.conf
                # before giving up. Lower it in config file and try it first as
                # it will only reach timeout on VMs with only IPv6 addresses.
                with EphemeralDHCPv4(
                    self.distro,
                    self.distro.fallback_interface,
                ) as ipv4:
                    util.log_time(
                        logfunc=LOG.debug,
                        msg="Set api-metadata URL depending on "
                        "IPv4 availability",
                        func=self._set_metadata_url,
                        args=(self.metadata_urls,),
                    )
                    util.log_time(
                        logfunc=LOG.debug,
                        msg="Crawl of metadata service",
                        func=self._crawl_metadata,
                    )
                    self.ephemeral_fixed_address = ipv4["fixed-address"]
                    self.metadata["net_in_use"] = "ipv4"
            except (
                NoDHCPLeaseError,
                ConnectionError,
                ProcessExecutionError,
            ) as e:
                util.logexc(LOG, str(e))
                # DHCPv4 timeout means that there is no DHCPv4 on the NIC.
                # Flag it so we do not try to crawl on IPv4 again.
                self.has_ipv4 = False

        # Only crawl metadata on IPv6 if it has not been done on IPv4
        if not self.has_ipv4:
            try:
                with EphemeralIPv6Network(
                    self.distro,
                    self.distro.fallback_interface,
                ):
                    util.log_time(
                        logfunc=LOG.debug,
                        msg="Set api-metadata URL depending on "
                        "IPv6 availability",
                        func=self._set_metadata_url,
                        args=(self.metadata_urls,),
                    )
                    util.log_time(
                        logfunc=LOG.debug,
                        msg="Crawl of metadata service",
                        func=self._crawl_metadata,
                    )
                    self.metadata["net_in_use"] = "ipv6"
            except (ConnectionError):
                return False
        return True

    @property
    def network_config(self):
        """
        Configure networking according to data received from the
        metadata API.
        """
        if self._network_config is None:
            LOG.warning(
                "Found None as cached _network_config. Resetting to %s",
                sources.UNSET,
            )
            self._network_config = sources.UNSET

        if self._network_config != sources.UNSET:
            return self._network_config

        if self.metadata["private_ip"] is None:
            # New method of network configuration

            netcfg = {}
            ip_cfg = {}
            for ip in self.metadata["public_ips"]:
                # Use DHCP for primary address
                if ip["address"] == self.ephemeral_fixed_address:
                    ip_cfg["dhcp4"] = True
                    # Force addition of a route to the metadata API
                    ip_cfg["routes"] = [
                        {"to": "169.254.42.42/32", "via": "62.210.0.1"}
                    ]
                else:
                    if "addresses" in ip_cfg.keys():
                        ip_cfg["addresses"] += (
                            f'{ip["address"]}/{ip["netmask"]}',
                        )
                    else:
                        ip_cfg["addresses"] = (
                            f'{ip["address"]}/{ip["netmask"]}',
                        )
                    if ip["family"] == "inet6":
                        route = {"via": ip["gateway"], "to": "::/0"}
                        if "routes" in ip_cfg.keys():
                            ip_cfg["routes"] += [route]
                        else:
                            ip_cfg["routes"] = [route]
            netcfg[self.distro.fallback_interface] = ip_cfg
            self._network_config = {"version": 2, "ethernets": netcfg}
        else:
            # Kept for backward compatibility
            netcfg = {
                "type": "physical",
                "name": "%s" % self.distro.fallback_interface,
            }
            subnets = [{"type": "dhcp4"}]
            if self.metadata["ipv6"]:
                subnets += [
                    {
                        "type": "static",
                        "address": "%s" % self.metadata["ipv6"]["address"],
                        "netmask": "%s" % self.metadata["ipv6"]["netmask"],
                        "routes": [
                            {
                                "network": "::",
                                "prefix": "0",
                                "gateway": "%s"
                                % self.metadata["ipv6"]["gateway"],
                            }
                        ],
                    }
                ]
            netcfg["subnets"] = subnets
            self._network_config = {"version": 1, "config": [netcfg]}
        LOG.debug("network_config : %s", self._network_config)
        return self._network_config

    @property
    def launch_index(self):
        return None

    def get_instance_id(self):
        return self.metadata["id"]

    def get_public_ssh_keys(self):
        ssh_keys = [key["key"] for key in self.metadata["ssh_public_keys"]]

        akeypre = "AUTHORIZED_KEY="
        plen = len(akeypre)
        for tag in self.metadata.get("tags", []):
            if not tag.startswith(akeypre):
                continue
            ssh_keys.append(tag[plen:].replace("_", " "))

        return ssh_keys

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        return DataSourceHostname(self.metadata["hostname"], False)

    @property
    def availability_zone(self):
        return None

    @property
    def region(self):
        return None


datasources = [
    (DataSourceScaleway, (sources.DEP_FILESYSTEM,)),
]


def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
