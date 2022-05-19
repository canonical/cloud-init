# Author: Mathieu Corbin <mathieu.corbin@exoscale.com>
# Author: Christopher Glass <christopher.glass@exoscale.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import dmi, helpers
from cloudinit import log as logging
from cloudinit import sources, url_helper, util
from cloudinit.sources.helpers import ec2

LOG = logging.getLogger(__name__)

METADATA_URL = "http://169.254.169.254"
API_VERSION = "1.0"
PASSWORD_SERVER_PORT = 8080

URL_TIMEOUT = 10
URL_RETRIES = 6

EXOSCALE_DMI_NAME = "Exoscale"


class DataSourceExoscale(sources.DataSource):

    dsname = "Exoscale"

    url_max_wait = 120

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceExoscale, self).__init__(sys_cfg, distro, paths)
        LOG.debug("Initializing the Exoscale datasource")

        self.metadata_url = self.ds_cfg.get("metadata_url", METADATA_URL)
        self.api_version = self.ds_cfg.get("api_version", API_VERSION)
        self.password_server_port = int(
            self.ds_cfg.get("password_server_port", PASSWORD_SERVER_PORT)
        )
        self.url_timeout = self.ds_cfg.get("timeout", URL_TIMEOUT)
        self.url_retries = self.ds_cfg.get("retries", URL_RETRIES)
        self.extra_config = {}

    def activate(self, cfg, is_new_instance):
        """Adjust set-passwords module to run 'always' during each boot"""
        # We run the set password config module on every boot in order to
        # enable resetting the instance's password via the exoscale console
        # (and a subsequent instance reboot).
        # Exoscale password server only provides set-passwords user-data if
        # a user has triggered a password reset. So calling that password
        # service generally results in no additional cloud-config.
        # TODO(Create util functions for overriding merged sys_cfg module freq)
        mod = "set_passwords"
        sem_path = self.paths.get_ipath_cur("sem")
        sem_helper = helpers.FileSemaphores(sem_path)
        if sem_helper.clear("config_" + mod, None):
            LOG.debug("Overriding module set-passwords with frequency always")

    def wait_for_metadata_service(self):
        """Wait for the metadata service to be reachable."""

        metadata_url = "{}/{}/meta-data/instance-id".format(
            self.metadata_url, self.api_version
        )

        url, _response = url_helper.wait_for_url(
            urls=[metadata_url],
            max_wait=self.url_max_wait,
            timeout=self.url_timeout,
            status_cb=LOG.critical,
        )

        return bool(url)

    def crawl_metadata(self):
        """
        Crawl the metadata service when available.

        @returns: Dictionary of crawled metadata content.
        """
        metadata_ready = util.log_time(
            logfunc=LOG.info,
            msg="waiting for the metadata service",
            func=self.wait_for_metadata_service,
        )

        if not metadata_ready:
            return {}

        return read_metadata(
            self.metadata_url,
            self.api_version,
            self.password_server_port,
            self.url_timeout,
            self.url_retries,
        )

    def _get_data(self):
        """Fetch the user data, the metadata and the VM password
        from the metadata service.

        Please refer to the datasource documentation for details on how the
        metadata server and password server are crawled.
        """
        if not self._is_platform_viable():
            return False

        data = util.log_time(
            logfunc=LOG.debug,
            msg="Crawl of metadata service",
            func=self.crawl_metadata,
        )

        if not data:
            return False

        self.userdata_raw = data["user-data"]
        self.metadata = data["meta-data"]
        password = data.get("password")

        password_config = {}
        if password:
            # Since we have a password, let's make sure we are allowed to use
            # it by allowing ssh_pwauth.
            # The password module's default behavior is to leave the
            # configuration as-is in this regard, so that means it will either
            # leave the password always disabled if no password is ever set, or
            # leave the password login enabled if we set it once.
            password_config = {
                "ssh_pwauth": True,
                "password": password,
                "chpasswd": {
                    "expire": False,
                },
            }

        # builtin extra_config overrides password_config
        self.extra_config = util.mergemanydict(
            [self.extra_config, password_config]
        )

        return True

    def get_config_obj(self):
        return self.extra_config

    def _is_platform_viable(self):
        return dmi.read_dmi_data("system-product-name").startswith(
            EXOSCALE_DMI_NAME
        )


# Used to match classes to dependencies
datasources = [
    (DataSourceExoscale, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)


def get_password(
    metadata_url=METADATA_URL,
    api_version=API_VERSION,
    password_server_port=PASSWORD_SERVER_PORT,
    url_timeout=URL_TIMEOUT,
    url_retries=URL_RETRIES,
):
    """Obtain the VM's password if set.

    Once fetched the password is marked saved. Future calls to this method may
    return empty string or 'saved_password'."""
    password_url = "{}:{}/{}/".format(
        metadata_url, password_server_port, api_version
    )
    response = url_helper.read_file_or_url(
        password_url,
        ssl_details=None,
        headers={"DomU_Request": "send_my_password"},
        timeout=url_timeout,
        retries=url_retries,
    )
    password = response.contents.decode("utf-8")
    # the password is empty or already saved
    # Note: the original metadata server would answer an additional
    # 'bad_request' status, but the Exoscale implementation does not.
    if password in ["", "saved_password"]:
        return None
    # save the password
    url_helper.read_file_or_url(
        password_url,
        ssl_details=None,
        headers={"DomU_Request": "saved_password"},
        timeout=url_timeout,
        retries=url_retries,
    )
    return password


def read_metadata(
    metadata_url=METADATA_URL,
    api_version=API_VERSION,
    password_server_port=PASSWORD_SERVER_PORT,
    url_timeout=URL_TIMEOUT,
    url_retries=URL_RETRIES,
):
    """Query the metadata server and return the retrieved data."""
    crawled_metadata = {}
    crawled_metadata["_metadata_api_version"] = api_version
    try:
        crawled_metadata["user-data"] = ec2.get_instance_userdata(
            api_version, metadata_url, timeout=url_timeout, retries=url_retries
        )
        crawled_metadata["meta-data"] = ec2.get_instance_metadata(
            api_version, metadata_url, timeout=url_timeout, retries=url_retries
        )
    except Exception as e:
        util.logexc(
            LOG, "failed reading from metadata url %s (%s)", metadata_url, e
        )
        return {}

    try:
        crawled_metadata["password"] = get_password(
            api_version=api_version,
            metadata_url=metadata_url,
            password_server_port=password_server_port,
            url_retries=url_retries,
            url_timeout=url_timeout,
        )
    except Exception as e:
        util.logexc(
            LOG,
            "failed to read from password server url %s:%s (%s)",
            metadata_url,
            password_server_port,
            e,
        )

    return crawled_metadata


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Query Exoscale Metadata")
    parser.add_argument(
        "--endpoint",
        metavar="URL",
        help="The url of the metadata service.",
        default=METADATA_URL,
    )
    parser.add_argument(
        "--version",
        metavar="VERSION",
        help="The version of the metadata endpoint to query.",
        default=API_VERSION,
    )
    parser.add_argument(
        "--retries",
        metavar="NUM",
        type=int,
        help="The number of retries querying the endpoint.",
        default=URL_RETRIES,
    )
    parser.add_argument(
        "--timeout",
        metavar="NUM",
        type=int,
        help="The time in seconds to wait before timing out.",
        default=URL_TIMEOUT,
    )
    parser.add_argument(
        "--password-port",
        metavar="PORT",
        type=int,
        help="The port on which the password endpoint listens",
        default=PASSWORD_SERVER_PORT,
    )

    args = parser.parse_args()

    data = read_metadata(
        metadata_url=args.endpoint,
        api_version=args.version,
        password_server_port=args.password_port,
        url_timeout=args.timeout,
        url_retries=args.retries,
    )

    print(util.json_dumps(data))

# vi: ts=4 expandtab
