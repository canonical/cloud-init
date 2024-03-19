# This file is part of cloud-init. See LICENSE file for license information.

import base64
import json
import logging
from typing import Optional
from requests.exceptions import ConnectionError
from cloudinit import atomic_helper, dmi, helpers
from cloudinit import net, sources, url_helper, util
from cloudinit.sources.helpers import ec2
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralDHCPv4, EphemeralIPNetwork

LOG = logging.getLogger(__name__)

METADATA_URLS = ["http://169.254.169.254"]

METADATA_VERSION = 2

URL_MAX_WAIT = 5
URL_TIMEOUT = 5
URL_RETRIES = 6


class DataSourceCloudCIX(sources.DataSource):

    dsname = "CloudCIX"

    _metadata_url: str

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceCloudCIX, self).__init__(sys_cfg, distro, paths)
        LOG.debug("Initializing the CIX datasource")
        self._metadata_url = None
        self.max_wait = URL_MAX_WAIT
        self.url_timeout = URL_TIMEOUT

    def _get_data(self):
        """Fetch the user data, the metadata and the VM password
        from the metadata service.

        Please refer to the datasource documentation for details on how the
        metadata server and password server are crawled.
        """
        try:
            with EphemeralIPNetwork(
                self.distro, interface=net.find_fallback_nic(), ipv6=True, ipv4=True
            ):
                crawled_data = util.log_time(
                    logfunc=LOG.debug,
                    msg=f"Crawl of metadata service",
                    func=self.crawl_metadata_service,
                )
        except NoDHCPLeaseError as e:
            LOG.error("Bailing, DHCP exception: %s", e)
            return False

        if not crawled_data:
            return False

        self.metadata = crawled_data["metadata"]
        self.userdata_raw = crawled_data["userdata_raw"]

        return True

    def crawl_metadata_service(self) -> dict:
        # Wait for metadata server
        md_url = self.determine_md_url()
        if md_url is None:
            return {}

        data = {}
        data["metadata"] = read_metadata(md_url)
        if data["metadata"] is None:
            return {}

        data["userdata_raw"] = read_userdata_raw(md_url)
        if data["userdata_raw"] is None:
            return {}

        return data

    def determine_md_url(self) -> Optional[str]:
        if self._metadata_url:
            return self._metadata_url

        # Try to reach the metadata server
        base_url, _ = url_helper.wait_for_url(
            METADATA_URLS,
            max_wait=self.max_wait,
            timeout=self.url_timeout,
        )
        if not base_url:
            return None

        # Find the highest supported metadata version
        md_url = None
        for version in range(METADATA_VERSION, 0, -1):
            url = url_helper.combine_url(base_url, "v{0}".format(version), "metadata")
            try:
                response = url_helper.readurl(url, timeout=self.url_timeout)
            except url_helper.UrlError as e:
                LOG.debug("URL %s raised exception %s", url, e)
                continue

            if response.ok():
                md_url = url_helper.combine_url(base_url, "v{0}".format(version))
                break
            else:
                LOG.debug("No metadata found at URL %s", url)

        self._metadata_url = md_url
        return self._metadata_url

    @staticmethod
    def ds_detect():
        product_name = dmi.read_dmi_data("system-product")
        if product_name == self.dsname:
            return True

        return False

    @property
    def network_config(self):
        if self._net_cfg:
            return self._net_cfg

        if not self.metadata:
            return None
        self._net_cfg = self._generate_net_cfg(self.metadata)
        return self._net_cfg

    def _generate_net_cfg(self, metadata):
        netcfg = {"version": 2, "ethernets": {}}
        macs_to_nics = net.get_interfaces_by_mac()

        interface_map = {}
        for iface in metadata["network"]["interfaces"]:
            name = macs_to_nics.get(iface["mac_address"])
            if name is None:
                LOG.warning("Metadata mac address %s not found.", iface["mac_address"])
                continue
            interfaces["name"] = iface

        for name, iface in interfaces.items():
            netcfg["ethernets"][name] = {
                "set-name": name,
                "match": {
                    "macaddress": iface["mac_address"].lower(),
                },
                "addresses": iface["addresses"]
            }

        return netcfg


def read_metadata(md_url) -> Optional[str]:
    url = url_helper.combine_url(md_url, "metadata")
    try:
        response = url_helper.readurl(url)
        metadata = json.loads(response.contents.decode())
    except (url_helper.UrlError, json.JSONDecodeError) as e:
        LOG.warning("Failed to read metadata. Cause: %s", e)
        metadata = None
    return metadata


def read_userdata_raw(md_url) -> Optional[str]:
    url = url_helper.combine_url(md_url, "userdata")
    try:
        response = url_helper.readurl(url)
        userdata_raw = util.maybe_b64decode(response.contents)
    except url_helper.UrlError as e:
        LOG.warning("Failed to read userdata. Cause: %s", e)
        userdata_raw = None
    return userdata_raw


# Used to match classes to dependencies
datasources = [
    (DataSourceCloudCIX, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
