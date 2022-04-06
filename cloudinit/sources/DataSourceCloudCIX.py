import json

from cloudinit import dmi
from cloudinit import log as logging
from cloudinit import sources, url_helper, util

LOG = logging.getLogger(__name__)

DS_BASE_URL = "http://169.254.169.254/"

URL_TIMEOUT = 10
URL_RETRIES = 5
URL_SEC_BETWEEN_RETRIES = 1


class DataSourceCloudCIX(sources.DataSource):

    dsname = "CloudCIX"

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceCloudCIX, self).__init__(sys_cfg, distro, paths)

        self.base_url = url_helper.combine_url(DS_BASE_URL, "v1")
        self.url_timeout = self.ds_cfg.get("timeout", URL_TIMEOUT)
        self.url_retries = self.ds_cfg.get("retries", URL_RETRIES)
        self.wait_retry = self.ds_cfg.get(
            "wait_retry", URL_SEC_BETWEEN_RETRIES
        )

    def _get_data(self):
        if not self.is_running_in_cloudcix():
            return False

        try:
            md = util.log_time(
                LOG.debug,
                "Crawl of CloudCIX metadata service",
                read_metadata,
                kwargs={
                    "base_url": self.base_url,
                    "url_params": self.get_url_params(),
                },
            )
        except sources.InvalidMetaDataException as error:
            LOG.debug(
                "Failed to read data from CloudCIX datasource: %s", error
            )
            return False

        self.metadata = md["meta-data"]
        self.userdata_raw = md["user-data"]
        return True

    def is_running_in_cloudcix(self):
        return dmi.read_dmi_data("system-product-name") == self.dsname


def read_metadata(base_url, url_params):
    md = {}
    leaf_key_format_callback = (
        ("metadata", "meta-data", util.load_json),
        ("userdata", "user-data", util.decode_binary),
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


# vi: ts=4 expandtab
