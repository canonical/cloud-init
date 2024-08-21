# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
from typing import Optional

from cloudinit import dmi, net, sources, url_helper, util
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralIPNetwork

LOG = logging.getLogger(__name__)

METADATA_URLS = ["http://169.254.169.254"]
METADATA_VERSION = 1

CLOUDCIX_DMI_NAME = "CloudCIX"


class DataSourceCloudCIX(sources.DataSource):

    dsname = "CloudCIX"
    # Setup read_url parameters through get_url_params()
    url_retries = 3
    url_timeout_seconds = 5
    url_sec_between_retries = 5

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceCloudCIX, self).__init__(sys_cfg, distro, paths)
        self.distro = distro
        self._metadata_url = None
        self._net_cfg = None

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        if not hasattr(self, "_metadata_url"):
            setattr(self, "_metadata_url", None)
        if not hasattr(self, "_net_cfg"):
            setattr(self, "_net_cfg", None)

    def _get_data(self):
        """
        Fetch the user data and the metadata
        """
        try:
            netw = EphemeralIPNetwork(
                self.distro,
                interface=net.find_fallback_nic(),
                ipv6=True,
                ipv4=True,
            )
            state_msg = f" {netw.state_msg}" if netw.state_msg else ""
            crawled_data = util.log_time(
                logfunc=LOG.debug,
                msg=f"Crawl of metadata service{state_msg}",
                func=self.crawl_metadata_service,
            )
        except NoDHCPLeaseError as e:
            LOG.error("Bailing, DHCP exception: %s", e)
            return False
        except sources.InvalidMetaDataException as error:
            LOG.debug(
                "Failed to read data from CloudCIX datasource: %s", error
            )
            return False

        self.metadata = crawled_data["meta-data"]
        self.userdata_raw = util.decode_binary(crawled_data["user-data"])

        return True

    def crawl_metadata_service(self) -> dict:
        md_url = self.determine_md_url()
        if md_url is None:
            raise sources.InvalidMetaDataException(
                "Could not determine MetaData url"
            )

        data = read_metadata(md_url, self.get_url_params())
        return data

    def determine_md_url(self) -> Optional[str]:
        if self._metadata_url:
            return self._metadata_url

        # Try to reach the metadata server
        url_params = self.get_url_params()
        base_url, _ = url_helper.wait_for_url(
            METADATA_URLS,
            max_wait=url_params.max_wait_seconds,
            timeout=url_params.timeout_seconds,
        )
        if not base_url:
            return None

        # Find the highest supported metadata version
        md_url = None
        for version in range(METADATA_VERSION, 0, -1):
            url = url_helper.combine_url(
                base_url, "v{0}".format(version), "metadata"
            )
            try:
                response = url_helper.readurl(url, timeout=self.url_timeout)
            except url_helper.UrlError as e:
                LOG.debug("URL %s raised exception %s", url, e)
                continue

            if response.ok():
                md_url = url_helper.combine_url(
                    base_url, "v{0}".format(version)
                )
                break
            else:
                LOG.debug("No metadata found at URL %s", url)

        self._metadata_url = md_url
        return self._metadata_url

    @staticmethod
    def ds_detect():
        return is_platform_viable()

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

        for iface in metadata["network"]["interfaces"]:
            name = macs_to_nics.get(iface["mac_address"])
            if name is None:
                LOG.warning(
                    "Metadata mac address %s not found.", iface["mac_address"]
                )
                continue
            netcfg["ethernets"][name] = {
                "set-name": name,
                "match": {
                    "macaddress": iface["mac_address"].lower(),
                },
                "addresses": iface["addresses"],
            }

        return netcfg


def is_platform_viable() -> bool:
    return dmi.read_dmi_data("system-product-name") == CLOUDCIX_DMI_NAME


def read_metadata(base_url, url_params):
    md = {}
    leaf_key_format_callback = (
        ("metadata", "meta-data", util.load_json),
        ("userdata", "user-data", util.maybe_b64decode),
    )

    for url_leaf, new_key, format_callback in leaf_key_format_callback:
        try:
            response = url_helper.readurl(
                url=url_helper.combine_url(base_url, url_leaf),
                retries=url_params.num_retries,
                sec_between=url_params.sec_between_retries,
                timeout=url_params.timeout_seconds,
            )
        except url_helper.UrlError as error:
            raise sources.InvalidMetaDataException(
                f"Failed to fetch IMDS {url_leaf}: "
                f"{base_url}/{url_leaf}: {error}"
            )

        if not response.ok():
            raise sources.InvalidMetaDataException(
                f"No valid {url_leaf} found. "
                f"URL {base_url}/{url_leaf} returned code {response.code}"
            )

        try:
            md[new_key] = format_callback(response.contents)
        except json.decoder.JSONDecodeError as exc:
            raise sources.InvalidMetaDataException(
                f"Invalid JSON at {base_url}/{url_leaf}: {exc}"
            ) from exc
    return md


# Used to match classes to dependencies
datasources = [
    (DataSourceCloudCIX, (sources.DEP_FILESYSTEM,)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
