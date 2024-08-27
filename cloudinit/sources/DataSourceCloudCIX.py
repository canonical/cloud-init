# This file is part of cloud-init. See LICENSE file for license information.

import json
import logging
from typing import Optional

from cloudinit import dmi, sources, url_helper, util

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
        self._metadata_url = None
        self._net_cfg = None

    def _get_data(self):
        """
        Fetch the user data and the metadata
        """
        try:
            crawled_data = self.crawl_metadata_service()
        except sources.InvalidMetaDataException as error:
            LOG.error(
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
                "Could not determine metadata URL"
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
                self._metadata_url = url_helper.combine_url(
                    base_url, "v{0}".format(version)
                )
                break
            else:
                LOG.debug("No metadata found at URL %s", url)

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
        self._net_cfg = self.metadata["network"]
        return self._net_cfg


def is_platform_viable() -> bool:
    return dmi.read_dmi_data("system-product-name") == CLOUDCIX_DMI_NAME


def read_metadata(base_url: str, url_params):
    """
    Read metadata from metadata server at base_url

    :returns: dictionary of retrieved metadata and user data containing the
              following keys: meta-data, user-data
    :param: base_url: meta data server's base URL
    :param: url_params: dictionary of URL retrieval parameters. Valid keys are
            `retries`, `sec_between` and `timeout`.
    :raises: InvalidMetadataException upon network error connecting to metadata
             URL, error response from meta data server or failure to
             decode/parse metadata and userdata payload.
    """
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
    (DataSourceCloudCIX, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
