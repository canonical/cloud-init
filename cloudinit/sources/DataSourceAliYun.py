# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
from typing import List, Union

from cloudinit import dmi, sources
from cloudinit import url_helper as uhelp
from cloudinit import util
from cloudinit.event import EventScope, EventType
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralIPNetwork
from cloudinit.sources import DataSourceHostname
from cloudinit.sources.helpers import aliyun, ec2

LOG = logging.getLogger(__name__)

ALIYUN_PRODUCT = "Alibaba Cloud ECS"


class DataSourceAliYun(sources.DataSource):

    dsname = "AliYun"
    metadata_urls = ["http://100.100.100.200"]

    # The minimum supported metadata_version from the ecs metadata apis
    min_metadata_version = "2016-01-01"
    extended_metadata_versions: List[str] = []

    # Setup read_url parameters per get_url_params.
    url_max_wait = 240
    url_timeout = 50

    # API token for accessing the metadata service
    _api_token = None
    # Used to cache calculated network cfg v1
    _network_config: Union[str, dict] = sources.UNSET

    # Whether we want to get network configuration from the metadata service.
    perform_dhcp_setup = False

    # Aliyun metadata server security enhanced mode overwrite
    @property
    def imdsv2_token_put_header(self):
        return "X-aliyun-ecs-metadata-token"

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceAliYun, self).__init__(sys_cfg, distro, paths)
        self.default_update_events = copy.deepcopy(self.default_update_events)
        self.default_update_events[EventScope.NETWORK].add(EventType.BOOT)

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        hostname = self.metadata.get("hostname")
        is_default = False
        if hostname is None:
            hostname = "localhost.localdomain"
            is_default = True
        return DataSourceHostname(hostname, is_default)

    def get_public_ssh_keys(self):
        return parse_public_keys(self.metadata.get("public-keys", {}))

    def _get_cloud_name(self):
        if _is_aliyun():
            return self.dsname.lower()
        return "NO_ALIYUN_METADATA"

    @property
    def platform(self):
        return self.dsname.lower()

    # IMDSv2 related parameters from the ecs metadata api document
    @property
    def api_token_route(self):
        return "latest/api/token"

    @property
    def imdsv2_token_ttl_seconds(self):
        return "21600"

    @property
    def imdsv2_token_redact(self):
        return [self.imdsv2_token_put_header, self.imdsv2_token_req_header]

    @property
    def imdsv2_token_req_header(self):
        return self.imdsv2_token_put_header + "-ttl-seconds"

    @property
    def network_config(self):
        """Return a network config dict for rendering ENI or netplan files."""
        if self._network_config != sources.UNSET:
            return self._network_config

        result = {}
        iface = self.distro.fallback_interface
        net_md = self.metadata.get("network")
        if isinstance(net_md, dict):
            result = aliyun.convert_ecs_metadata_network_config(
                net_md,
                fallback_nic=iface,
                full_network_config=util.get_cfg_option_bool(
                    self.ds_cfg, "apply_full_imds_network_config", True
                ),
            )
        else:
            LOG.warning("Metadata 'network' key not valid: %s.", net_md)
            return result
        self._network_config = result
        return self._network_config

    def _maybe_fetch_api_token(self, mdurls):
        """Get an API token for ECS Instance Metadata Service.

        On ECS. IMDS will always answer an API token, set
        HttpTokens=optional (default) when create instance will not forcefully
        use the security-enhanced mode (IMDSv2).

        https://api.alibabacloud.com/api/Ecs/2014-05-26/RunInstances
        """

        urls = []
        url2base = {}
        url_path = self.api_token_route
        request_method = "PUT"
        for url in mdurls:
            cur = "{0}/{1}".format(url, url_path)
            urls.append(cur)
            url2base[cur] = url

        # use the self._imds_exception_cb to check for Read errors
        LOG.debug("Fetching Ecs IMDSv2 API Token")

        response = None
        url = None
        url_params = self.get_url_params()
        try:
            url, response = uhelp.wait_for_url(
                urls=urls,
                max_wait=url_params.max_wait_seconds,
                timeout=url_params.timeout_seconds,
                status_cb=LOG.warning,
                headers_cb=self._get_headers,
                exception_cb=self._imds_exception_cb,
                request_method=request_method,
                headers_redact=self.imdsv2_token_redact,
                connect_synchronously=False,
            )
        except uhelp.UrlError:
            # We use the raised exception to interupt the retry loop.
            # Nothing else to do here.
            pass

        if url and response:
            self._api_token = response
            return url2base[url]

        # If we get here, then wait_for_url timed out, waiting for IMDS
        # or the IMDS HTTP endpoint is disabled
        return None

    def wait_for_metadata_service(self):
        mcfg = self.ds_cfg
        mdurls = mcfg.get("metadata_urls", self.metadata_urls)

        # try the api token path first
        metadata_address = self._maybe_fetch_api_token(mdurls)

        if metadata_address:
            self.metadata_address = metadata_address
            LOG.debug("Using metadata source: '%s'", self.metadata_address)
        else:
            LOG.warning("IMDS's HTTP endpoint is probably disabled")
        return bool(metadata_address)

    def crawl_metadata(self):
        """Crawl metadata service when available.

        @returns: Dictionary of crawled metadata content containing the keys:
          meta-data, user-data, vendor-data and dynamic.
        """
        if not self.wait_for_metadata_service():
            return {}
        redact = self.imdsv2_token_redact
        crawled_metadata = {}
        exc_cb = self._refresh_stale_aliyun_token_cb
        exc_cb_ud = self._skip_or_refresh_stale_aliyun_token_cb
        skip_cb = None
        exe_cb_whole_meta = self._skip_json_path_meta_path_aliyun_cb
        try:
            crawled_metadata["user-data"] = aliyun.get_instance_data(
                self.min_metadata_version,
                self.metadata_address,
                headers_cb=self._get_headers,
                headers_redact=redact,
                exception_cb=exc_cb_ud,
                item_name="user-data",
            )
            crawled_metadata["vendor-data"] = aliyun.get_instance_data(
                self.min_metadata_version,
                self.metadata_address,
                headers_cb=self._get_headers,
                headers_redact=redact,
                exception_cb=exc_cb_ud,
                item_name="vendor-data",
            )
            try:
                result = aliyun.get_instance_meta_data(
                    self.min_metadata_version,
                    self.metadata_address,
                    headers_cb=self._get_headers,
                    headers_redact=redact,
                    exception_cb=exe_cb_whole_meta,
                )
                crawled_metadata["meta-data"] = result
            except Exception:
                util.logexc(
                    LOG,
                    "Faild read json meta-data from %s "
                    "fall back directory tree style",
                    self.metadata_address,
                )
                crawled_metadata["meta-data"] = ec2.get_instance_metadata(
                    self.min_metadata_version,
                    self.metadata_address,
                    headers_cb=self._get_headers,
                    headers_redact=redact,
                    exception_cb=exc_cb,
                    retrieval_exception_ignore_cb=skip_cb,
                )
        except Exception:
            util.logexc(
                LOG,
                "Failed reading from metadata address %s",
                self.metadata_address,
            )
            return {}
        return crawled_metadata

    def _refresh_stale_aliyun_token_cb(self, msg, exception):
        """Exception handler for Ecs to refresh token if token is stale."""
        if isinstance(exception, uhelp.UrlError) and exception.code == 401:
            # With _api_token as None, _get_headers will _refresh_api_token.
            LOG.debug("Clearing cached Ecs API token due to expiry")
            self._api_token = None
        return True  # always retry

    def _skip_retry_on_codes(self, status_codes, cause):
        """Returns False if cause.code is in status_codes."""
        return cause.code not in status_codes

    def _skip_or_refresh_stale_aliyun_token_cb(self, msg, exception):
        """Callback will not retry on SKIP_USERDATA_VENDORDATA_CODES or
        if no token is available."""
        retry = self._skip_retry_on_codes(ec2.SKIP_USERDATA_CODES, exception)
        if not retry:
            return False  # False raises exception
        return self._refresh_stale_aliyun_token_cb(msg, exception)

    def _skip_json_path_meta_path_aliyun_cb(self, msg, exception):
        """Callback will not retry of whole meta_path is not found"""
        if isinstance(exception, uhelp.UrlError) and exception.code == 404:
            LOG.warning("whole meta_path is not found, skipping")
            return False
        return self._refresh_stale_aliyun_token_cb(msg, exception)

    def _get_data(self):
        if self.cloud_name != self.dsname.lower():
            return False
        if self.perform_dhcp_setup:  # Setup networking in init-local stage.
            if util.is_FreeBSD():
                LOG.debug("FreeBSD doesn't support running dhclient with -sf")
                return False
            try:
                with EphemeralIPNetwork(
                    self.distro,
                    self.distro.fallback_interface,
                    ipv4=True,
                    ipv6=False,
                ) as netw:
                    self._crawled_metadata = self.crawl_metadata()
                    LOG.debug(
                        "Crawled metadata service%s",
                        f" {netw.state_msg}" if netw.state_msg else "",
                    )

            except NoDHCPLeaseError:
                return False
        else:
            self._crawled_metadata = self.crawl_metadata()
        if not self._crawled_metadata or not isinstance(
            self._crawled_metadata, dict
        ):
            return False
        self.metadata = self._crawled_metadata.get("meta-data", {})
        self.userdata_raw = self._crawled_metadata.get("user-data", {})
        self.vendordata_raw = self._crawled_metadata.get("vendor-data", {})
        return True

    def _refresh_api_token(self, seconds=None):
        """Request new metadata API token.
        @param seconds: The lifetime of the token in seconds

        @return: The API token or None if unavailable.
        """

        if seconds is None:
            seconds = self.imdsv2_token_ttl_seconds

        LOG.debug("Refreshing Ecs metadata API token")
        request_header = {self.imdsv2_token_req_header: seconds}
        token_url = "{}/{}".format(self.metadata_address, self.api_token_route)
        try:
            response = uhelp.readurl(
                token_url,
                headers=request_header,
                headers_redact=self.imdsv2_token_redact,
                request_method="PUT",
            )
        except uhelp.UrlError as e:
            LOG.warning(
                "Unable to get API token: %s raised exception %s", token_url, e
            )
            return None
        return response.contents

    def _get_headers(self, url=""):
        """Return a dict of headers for accessing a url.

        If _api_token is unset on AWS, attempt to refresh the token via a PUT
        and then return the updated token header.
        """

        request_token_header = {
            self.imdsv2_token_req_header: self.imdsv2_token_ttl_seconds
        }
        if self.api_token_route in url:
            return request_token_header
        if not self._api_token:
            # If we don't yet have an API token, get one via a PUT against
            # api_token_route. This _api_token may get unset by a 403 due
            # to an invalid or expired token
            self._api_token = self._refresh_api_token()
            if not self._api_token:
                return {}
        return {self.imdsv2_token_put_header: self._api_token}

    def _imds_exception_cb(self, exception=None):
        """Fail quickly on proper AWS if IMDSv2 rejects API token request

        Guidance from Amazon is that if IMDSv2 had disabled token requests
        by returning a 403, or cloud-init malformed requests resulting in
        other 40X errors, we want the datasource detection to fail quickly
        without retries as those symptoms will likely not be resolved by
        retries.

        Exceptions such as requests.ConnectionError due to IMDS being
        temporarily unroutable or unavailable will still retry due to the
        callsite wait_for_url.
        """
        if isinstance(exception, uhelp.UrlError):
            # requests.ConnectionError will have exception.code == None
            if exception.code and exception.code >= 400:
                if exception.code == 403:
                    LOG.warning(
                        "Ecs IMDS endpoint returned a 403 error. "
                        "HTTP endpoint is disabled. Aborting."
                    )
                else:
                    LOG.warning(
                        "Fatal error while requesting Ecs IMDSv2 API tokens"
                    )
                raise exception
        return True


def _is_aliyun():
    return dmi.read_dmi_data("system-product-name") == ALIYUN_PRODUCT


def parse_public_keys(public_keys):
    keys = []
    for _key_id, key_body in public_keys.items():
        if isinstance(key_body, str):
            keys.append(key_body.strip())
        elif isinstance(key_body, list):
            keys.extend(key_body)
        elif isinstance(key_body, dict):
            key = key_body.get("openssh-key", [])
            if isinstance(key, str):
                keys.append(key.strip())
            elif isinstance(key, list):
                keys.extend(key)
    return keys


class DataSourceAliYunLocal(DataSourceAliYun):
    """Datasource run at init-local which sets up network to query metadata.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """

    perform_dhcp_setup = True


# Used to match classes to dependencies
datasources = [
    (DataSourceAliYunLocal, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceAliYun, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
