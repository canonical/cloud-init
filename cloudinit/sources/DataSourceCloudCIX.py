import json
import logging

from cloudinit import dmi, sources, url_helper

LOG = logging.getLogger(__name__)


class DataSourceCloudCIX(sources.DataSource):

    dsname = "CloudCIX"
    base_url = "http://169.254.169.254"

    def _get_data(self):
        """
        Datasources implement _get_data to setup metadata and userdata_raw.

        Minimally, the datasource should return a boolean True on success.
        Subclasses of DataSource must implement _get_data which sets self.metadata,
        vendordata_raw and userdata_raw.
        """
        if not self.is_running_in_cloudcix():
            return False

        self.metadata = self.read_metadata()
        self.userdata_raw = self.read_userdata()

        return True

    def is_running_in_cloudcix(self):
        return dmi.read_dmi_data("system-product-name") == self.dsname

    def read_metadata(self):
        metadata_url = url_helper.combine_url(self.base_url, "metadata")
        return self.read_url(metadata_url)

    def read_userdata(self):
        userdata_url = url_helper.combine_url(self.base_url, "userdata")
        return self.read_url(userdata_url)

    def read_url(self, url):
        response = url_helper.readurl(
            url,
            timeout=self.url_timeout,
            sec_between=self.url_sec_between_retries,
            retries=self.url_retries,
        )
        if not response.ok():
            raise RuntimeError("unable to read metadata at %s" % url)
        return json.loads(response.contents.decode())


# Used to match classes to dependencies
datasources = [
    (DataSourceCloudCIX, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


# vi: ts=4 expandtab
