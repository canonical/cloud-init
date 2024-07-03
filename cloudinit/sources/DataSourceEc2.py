# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Hafliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import copy
import logging
import os
import time
import uuid
from contextlib import suppress
from typing import Dict, List

from cloudinit import dmi, net, sources
from cloudinit import url_helper as uhelp
from cloudinit import util, warnings
from cloudinit.distros import Distro
from cloudinit.event import EventScope, EventType
from cloudinit.net import netplan
from cloudinit.net.dhcp import NoDHCPLeaseError
from cloudinit.net.ephemeral import EphemeralIPNetwork
from cloudinit.sources import NicOrder
from cloudinit.sources.helpers import ec2

LOG = logging.getLogger(__name__)

STRICT_ID_PATH = ("datasource", "Ec2", "strict_id")
STRICT_ID_DEFAULT = "warn"


class CloudNames:
    ALIYUN = "aliyun"
    AWS = "aws"
    BRIGHTBOX = "brightbox"
    ZSTACK = "zstack"
    E24CLOUD = "e24cloud"
    OUTSCALE = "outscale"
    # UNKNOWN indicates no positive id.  If strict_id is 'warn' or 'false',
    # then an attempt at the Ec2 Metadata service will be made.
    UNKNOWN = "unknown"
    # NO_EC2_METADATA indicates this platform does not have a Ec2 metadata
    # service available. No attempt at the Ec2 Metadata service will be made.
    NO_EC2_METADATA = "no-ec2-metadata"


# Drop when LP: #1988157 tag handling is fixed
def skip_404_tag_errors(exception):
    return exception.code == 404 and "meta-data/tags/" in exception.url


# Cloud platforms that support IMDSv2 style metadata server
IDMSV2_SUPPORTED_CLOUD_PLATFORMS = [CloudNames.AWS, CloudNames.ALIYUN]

# Only trigger hook-hotplug on NICs with Ec2 drivers. Avoid triggering
# it on docker virtual NICs and the like. LP: #1946003
_EXTRA_HOTPLUG_UDEV_RULES = """
ENV{ID_NET_DRIVER}=="vif|ena|ixgbevf", GOTO="cloudinit_hook"
GOTO="cloudinit_end"
"""


class DataSourceEc2(sources.DataSource):
    dsname = "Ec2"
    # Default metadata urls that will be used if none are provided
    # They will be checked for 'resolveability' and some of the
    # following may be discarded if they do not resolve
    metadata_urls = [
        "http://169.254.169.254",
        "http://[fd00:ec2::254]",
        "http://instance-data.:8773",
    ]

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = "2009-04-04"

    # Priority ordered list of additional metadata versions which will be tried
    # for extended metadata content. IPv6 support comes in 2016-09-02.
    # Tags support comes in 2021-03-23.
    extended_metadata_versions: List[str] = [
        "2021-03-23",
        "2018-09-24",
        "2016-09-02",
    ]

    # Setup read_url parameters per get_url_params.
    url_max_wait = 120
    url_timeout = 50

    _api_token = None  # API token for accessing the metadata service
    _network_config = sources.UNSET  # Used to cache calculated network cfg v1

    # Whether we want to get network configuration from the metadata service.
    perform_dhcp_setup = False

    supported_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.BOOT,
            EventType.BOOT_LEGACY,
            EventType.HOTPLUG,
        }
    }

    default_update_events = {
        EventScope.NETWORK: {
            EventType.BOOT_NEW_INSTANCE,
            EventType.HOTPLUG,
        }
    }

    extra_hotplug_udev_rules = _EXTRA_HOTPLUG_UDEV_RULES

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceEc2, self).__init__(sys_cfg, distro, paths)
        self.metadata_address = None
        self.identity = None
        self._fallback_nic_order = NicOrder.MAC

    def _unpickle(self, ci_pkl_version: int) -> None:
        super()._unpickle(ci_pkl_version)
        self.extra_hotplug_udev_rules = _EXTRA_HOTPLUG_UDEV_RULES
        self._fallback_nic_order = NicOrder.MAC

    def _get_cloud_name(self):
        """Return the cloud name as identified during _get_data."""
        return identify_platform()

    def _get_data(self):
        strict_mode, _sleep = read_strict_mode(
            util.get_cfg_by_path(
                self.sys_cfg, STRICT_ID_PATH, STRICT_ID_DEFAULT
            ),
            ("warn", None),
        )

        LOG.debug(
            "strict_mode: %s, cloud_name=%s cloud_platform=%s",
            strict_mode,
            self.cloud_name,
            self.platform,
        )
        if strict_mode == "true" and self.cloud_name == CloudNames.UNKNOWN:
            return False
        elif self.cloud_name == CloudNames.NO_EC2_METADATA:
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
                    ipv6=True,
                ) as netw:
                    state_msg = f" {netw.state_msg}" if netw.state_msg else ""
                    self._crawled_metadata = util.log_time(
                        logfunc=LOG.debug,
                        msg=f"Crawl of metadata service{state_msg}",
                        func=self.crawl_metadata,
                    )

            except NoDHCPLeaseError:
                return False
        else:
            self._crawled_metadata = util.log_time(
                logfunc=LOG.debug,
                msg="Crawl of metadata service",
                func=self.crawl_metadata,
            )
        if not self._crawled_metadata:
            return False
        self.metadata = self._crawled_metadata.get("meta-data", None)
        self.userdata_raw = self._crawled_metadata.get("user-data", None)
        self.identity = (
            self._crawled_metadata.get("dynamic", {})
            .get("instance-identity", {})
            .get("document", {})
        )
        return True

    def is_classic_instance(self):
        """Report if this instance type is Ec2 Classic (non-vpc)."""
        if not self.metadata:
            # Can return False on inconclusive as we are also called in
            # network_config where metadata will be present.
            # Secondary call site is in packaging postinst script.
            return False
        ifaces_md = self.metadata.get("network", {}).get("interfaces", {})
        for _mac, mac_data in ifaces_md.get("macs", {}).items():
            if "vpc-id" in mac_data:
                return False
        return True

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        return self.metadata.get("ami-launch-index")

    @property
    def platform(self):
        if not self._platform_type:
            self._platform_type = DataSourceEc2.dsname.lower()
        return self._platform_type

    # IMDSv2 related parameters from the ec2 metadata api document
    @property
    def api_token_route(self):
        return "latest/api/token"

    @property
    def imdsv2_token_ttl_seconds(self):
        return "21600"

    @property
    def imdsv2_token_put_header(self):
        return "X-aws-ec2-metadata-token"

    @property
    def imdsv2_token_req_header(self):
        return self.imdsv2_token_put_header + "-ttl-seconds"

    @property
    def imdsv2_token_redact(self):
        return [self.imdsv2_token_put_header, self.imdsv2_token_req_header]

    def get_metadata_api_version(self):
        """Get the best supported api version from the metadata service.

        Loop through all extended support metadata versions in order and
        return the most-fully featured metadata api version discovered.

        If extended_metadata_versions aren't present, return the datasource's
        min_metadata_version.
        """
        # Assumes metadata service is already up
        url_tmpl = "{0}/{1}/meta-data/instance-id"
        headers = self._get_headers()
        for api_ver in self.extended_metadata_versions:
            url = url_tmpl.format(self.metadata_address, api_ver)
            try:
                resp = uhelp.readurl(
                    url=url,
                    headers=headers,
                    headers_redact=self.imdsv2_token_redact,
                )
            except uhelp.UrlError as e:
                LOG.debug("url %s raised exception %s", url, e)
            else:
                if resp.code == 200:
                    LOG.debug("Found preferred metadata version %s", api_ver)
                    return api_ver
                elif resp.code == 404:
                    msg = "Metadata api version %s not present. Headers: %s"
                    LOG.debug(msg, api_ver, resp.headers)
        return self.min_metadata_version

    def get_instance_id(self):
        if self.cloud_name == CloudNames.AWS:
            # Prefer the ID from the instance identity document, but fall back
            if not getattr(self, "identity", None):
                # If re-using cached datasource, it's get_data run didn't
                # setup self.identity. So we need to do that now.
                api_version = self.get_metadata_api_version()
                self.identity = ec2.get_instance_identity(
                    api_version,
                    self.metadata_address,
                    headers_cb=self._get_headers,
                    headers_redact=self.imdsv2_token_redact,
                    exception_cb=self._refresh_stale_aws_token_cb,
                ).get("document", {})
            return self.identity.get(
                "instanceId", self.metadata["instance-id"]
            )
        else:
            return self.metadata["instance-id"]

    def _maybe_fetch_api_token(self, mdurls):
        """Get an API token for EC2 Instance Metadata Service.

        On EC2. IMDS will always answer an API token, unless
        the instance owner has disabled the IMDS HTTP endpoint or
        the network topology conflicts with the configured hop-limit.
        """
        if self.cloud_name not in IDMSV2_SUPPORTED_CLOUD_PLATFORMS:
            return

        urls = []
        url2base = {}
        url_path = self.api_token_route
        request_method = "PUT"
        for url in mdurls:
            cur = "{0}/{1}".format(url, url_path)
            urls.append(cur)
            url2base[cur] = url

        # use the self._imds_exception_cb to check for Read errors
        LOG.debug("Fetching Ec2 IMDSv2 API Token")

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
            # We use the raised exception to interrupt the retry loop.
            # Nothing else to do here.
            pass

        if url and response:
            self._api_token = response
            return url2base[url]

        # If we get here, then wait_for_url timed out, waiting for IMDS
        # or the IMDS HTTP endpoint is disabled
        return None

    def wait_for_metadata_service(self):
        urls = []
        start_time = 0
        mcfg = self.ds_cfg

        url_params = self.get_url_params()
        if url_params.max_wait_seconds <= 0:
            return False

        # Remove addresses from the list that wont resolve.
        mdurls = mcfg.get("metadata_urls", self.metadata_urls)
        filtered = [x for x in mdurls if util.is_resolvable_url(x)]

        if set(filtered) != set(mdurls):
            LOG.debug(
                "Removed the following from metadata urls: %s",
                list((set(mdurls) - set(filtered))),
            )

        if len(filtered):
            mdurls = filtered
        else:
            LOG.warning("Empty metadata url list! using default list")
            mdurls = self.metadata_urls

        # try the api token path first
        metadata_address = self._maybe_fetch_api_token(mdurls)
        # When running on EC2, we always access IMDS with an API token.
        # If we could not get an API token, then we assume the IMDS
        # endpoint was disabled and we move on without a data source.
        # Fallback to IMDSv1 if not running on EC2
        if (
            not metadata_address
            and self.cloud_name not in IDMSV2_SUPPORTED_CLOUD_PLATFORMS
        ):
            # if we can't get a token, use instance-id path
            url2base = {}
            url_path = "{ver}/meta-data/instance-id".format(
                ver=self.min_metadata_version
            )
            request_method = "GET"
            for url in mdurls:
                cur = "{0}/{1}".format(url, url_path)
                urls.append(cur)
                url2base[cur] = url

            start_time = time.monotonic()
            url, _ = uhelp.wait_for_url(
                urls=urls,
                max_wait=url_params.max_wait_seconds,
                timeout=url_params.timeout_seconds,
                status_cb=LOG.warning,
                headers_redact=self.imdsv2_token_redact,
                headers_cb=self._get_headers,
                request_method=request_method,
            )

            if url:
                metadata_address = url2base[url]

        if metadata_address:
            self.metadata_address = metadata_address
            LOG.debug("Using metadata source: '%s'", self.metadata_address)
        elif self.cloud_name in IDMSV2_SUPPORTED_CLOUD_PLATFORMS:
            LOG.warning("IMDS's HTTP endpoint is probably disabled")
        else:
            LOG.critical(
                "Giving up on md from %s after %s seconds",
                urls,
                int(time.monotonic() - start_time),
            )

        return bool(metadata_address)

    def device_name_to_device(self, name):
        # Consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        if "block-device-mapping" not in self.metadata:
            return None

        # Example:
        # 'block-device-mapping':
        # {'ami': '/dev/sda1',
        # 'ephemeral0': '/dev/sdb',
        # 'root': '/dev/sda1'}
        found = None
        bdm = self.metadata["block-device-mapping"]
        if not isinstance(bdm, dict):
            LOG.debug("block-device-mapping not a dictionary: '%s'", bdm)
            return None

        for entname, device in bdm.items():
            if entname == name:
                found = device
                break
            # LP: #513842 mapping in Euca has 'ephemeral' not 'ephemeral0'
            if entname == "ephemeral" and name == "ephemeral0":
                found = device

        if found is None:
            LOG.debug("Unable to convert %s to a device", name)
            return None

        ofound = found
        if not found.startswith("/"):
            found = "/dev/%s" % found

        if os.path.exists(found):
            return found

        remapped = self._remap_device(os.path.basename(found))
        if remapped:
            LOG.debug("Remapped device name %s => %s", found, remapped)
            return remapped

        # On t1.micro, ephemeral0 will appear in block-device-mapping from
        # metadata, but it will not exist on disk (and never will)
        # at this point, we've verified that the path did not exist
        # in the special case of 'ephemeral0' return None to avoid bogus
        # fstab entry (LP: #744019)
        if name == "ephemeral0":
            return None
        return ofound

    @property
    def availability_zone(self):
        try:
            if self.cloud_name == CloudNames.AWS:
                return self.identity.get(
                    "availabilityZone",
                    self.metadata["placement"]["availability-zone"],
                )
            else:
                return self.metadata["placement"]["availability-zone"]
        except KeyError:
            return None

    @property
    def region(self):
        if self.cloud_name == CloudNames.AWS:
            region = self.identity.get("region")
            # Fallback to trimming the availability zone if region is missing
            if self.availability_zone and not region:
                region = self.availability_zone[:-1]
            return region
        else:
            az = self.availability_zone
            if az is not None:
                return az[:-1]
        return None

    def activate(self, cfg, is_new_instance):
        if not is_new_instance:
            return
        if self.cloud_name == CloudNames.UNKNOWN:
            warn_if_necessary(
                util.get_cfg_by_path(cfg, STRICT_ID_PATH, STRICT_ID_DEFAULT),
                cfg,
            )

    @property
    def network_config(self):
        """Return a network config dict for rendering ENI or netplan files."""
        if self._network_config != sources.UNSET:
            return self._network_config

        if self.metadata is None:
            # this would happen if get_data hadn't been called. leave as UNSET
            LOG.warning(
                "Unexpected call to network_config when metadata is None."
            )
            return None

        result = None
        no_network_metadata_on_aws = bool(
            "network" not in self.metadata
            and self.cloud_name == CloudNames.AWS
        )
        if no_network_metadata_on_aws:
            LOG.debug(
                "Metadata 'network' not present:"
                " Refreshing stale metadata from prior to upgrade."
            )
            util.log_time(
                logfunc=LOG.debug,
                msg="Re-crawl of metadata service",
                func=self.get_data,
            )

        iface = self.distro.fallback_interface
        net_md = self.metadata.get("network")
        if isinstance(net_md, dict):
            # SRU_BLOCKER: xenial, bionic and eoan should default
            # apply_full_imds_network_config to False to retain original
            # behavior on those releases.
            result = convert_ec2_metadata_network_config(
                net_md,
                self.distro,
                fallback_nic=iface,
                full_network_config=util.get_cfg_option_bool(
                    self.ds_cfg, "apply_full_imds_network_config", True
                ),
                fallback_nic_order=self._fallback_nic_order,
            )

            # Non-VPC (aka Classic) Ec2 instances need to rewrite the
            # network config file every boot due to MAC address change.
            if self.is_classic_instance():
                self.default_update_events = copy.deepcopy(
                    self.default_update_events
                )
                self.default_update_events[EventScope.NETWORK].add(
                    EventType.BOOT
                )
                self.default_update_events[EventScope.NETWORK].add(
                    EventType.BOOT_LEGACY
                )
        else:
            LOG.warning("Metadata 'network' key not valid: %s.", net_md)
        self._network_config = result

        return self._network_config

    def crawl_metadata(self):
        """Crawl metadata service when available.

        @returns: Dictionary of crawled metadata content containing the keys:
          meta-data, user-data and dynamic.
        """
        if not self.wait_for_metadata_service():
            return {}
        api_version = self.get_metadata_api_version()
        redact = self.imdsv2_token_redact
        crawled_metadata = {}
        if self.cloud_name in IDMSV2_SUPPORTED_CLOUD_PLATFORMS:
            exc_cb = self._refresh_stale_aws_token_cb
            exc_cb_ud = self._skip_or_refresh_stale_aws_token_cb
            skip_cb = None
        elif self.cloud_name == CloudNames.OUTSCALE:
            exc_cb = exc_cb_ud = None
            skip_cb = skip_404_tag_errors
        else:
            exc_cb = exc_cb_ud = skip_cb = None
        try:
            raw_userdata = ec2.get_instance_userdata(
                api_version,
                self.metadata_address,
                headers_cb=self._get_headers,
                headers_redact=redact,
                exception_cb=exc_cb_ud,
            )
            crawled_metadata["user-data"] = util.maybe_b64decode(raw_userdata)
            crawled_metadata["meta-data"] = ec2.get_instance_metadata(
                api_version,
                self.metadata_address,
                headers_cb=self._get_headers,
                headers_redact=redact,
                exception_cb=exc_cb,
                retrieval_exception_ignore_cb=skip_cb,
            )
            if self.cloud_name == CloudNames.AWS:
                identity = ec2.get_instance_identity(
                    api_version,
                    self.metadata_address,
                    headers_cb=self._get_headers,
                    headers_redact=redact,
                    exception_cb=exc_cb,
                )
                crawled_metadata["dynamic"] = {"instance-identity": identity}
        except Exception:
            util.logexc(
                LOG,
                "Failed reading from metadata address %s",
                self.metadata_address,
            )
            return {}
        crawled_metadata["_metadata_api_version"] = api_version
        return crawled_metadata

    def _refresh_api_token(self, seconds=None):
        """Request new metadata API token.
        @param seconds: The lifetime of the token in seconds

        @return: The API token or None if unavailable.
        """
        if self.cloud_name not in IDMSV2_SUPPORTED_CLOUD_PLATFORMS:
            return None

        if seconds is None:
            seconds = self.imdsv2_token_ttl_seconds

        LOG.debug("Refreshing Ec2 metadata API token")
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

    def _skip_or_refresh_stale_aws_token_cb(self, msg, exception):
        """Callback will not retry on SKIP_USERDATA_CODES or if no token
        is available."""
        retry = ec2.skip_retry_on_codes(
            ec2.SKIP_USERDATA_CODES, msg, exception
        )
        if not retry:
            return False  # False raises exception
        return self._refresh_stale_aws_token_cb(msg, exception)

    def _refresh_stale_aws_token_cb(self, msg, exception):
        """Exception handler for Ec2 to refresh token if token is stale."""
        if isinstance(exception, uhelp.UrlError) and exception.code == 401:
            # With _api_token as None, _get_headers will _refresh_api_token.
            LOG.debug("Clearing cached Ec2 API token due to expiry")
            self._api_token = None
        return True  # always retry

    def _imds_exception_cb(self, msg, exception=None):
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
                        "Ec2 IMDS endpoint returned a 403 error. "
                        "HTTP endpoint is disabled. Aborting."
                    )
                else:
                    LOG.warning(
                        "Fatal error while requesting Ec2 IMDSv2 API tokens"
                    )
                raise exception

    def _get_headers(self, url=""):
        """Return a dict of headers for accessing a url.

        If _api_token is unset on AWS, attempt to refresh the token via a PUT
        and then return the updated token header.
        """
        if self.cloud_name not in IDMSV2_SUPPORTED_CLOUD_PLATFORMS:
            return {}
        # Request a 6 hour token if URL is api_token_route
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


class DataSourceEc2Local(DataSourceEc2):
    """Datasource run at init-local which sets up network to query metadata.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """

    perform_dhcp_setup = True  # Use dhcp before querying metadata

    def get_data(self):
        supported_platforms = (CloudNames.AWS, CloudNames.OUTSCALE)
        if self.cloud_name not in supported_platforms:
            LOG.debug(
                "Local Ec2 mode only supported on %s, not %s",
                supported_platforms,
                self.cloud_name,
            )
            return False
        return super(DataSourceEc2Local, self).get_data()


def read_strict_mode(cfgval, default):
    try:
        return parse_strict_mode(cfgval)
    except ValueError as e:
        LOG.warning(e)
        return default


def parse_strict_mode(cfgval):
    # given a mode like:
    #    true, false, warn,[sleep]
    # return tuple with string mode (true|false|warn) and sleep.
    if cfgval is True:
        return "true", None
    if cfgval is False:
        return "false", None

    if not cfgval:
        return "warn", 0

    mode, _, sleep = cfgval.partition(",")
    if mode not in ("true", "false", "warn"):
        raise ValueError(
            "Invalid mode '%s' in strict_id setting '%s': "
            "Expected one of 'true', 'false', 'warn'." % (mode, cfgval)
        )

    if sleep:
        try:
            sleep = int(sleep)
        except ValueError as e:
            raise ValueError(
                "Invalid sleep '%s' in strict_id setting '%s': not an integer"
                % (sleep, cfgval)
            ) from e
    else:
        sleep = None

    return mode, sleep


def warn_if_necessary(cfgval, cfg):
    try:
        mode, sleep = parse_strict_mode(cfgval)
    except ValueError as e:
        LOG.warning(e)
        return

    if mode == "false":
        return

    warnings.show_warning("non_ec2_md", cfg, mode=True, sleep=sleep)


def identify_aliyun(data):
    if data["product_name"] == "Alibaba Cloud ECS":
        return CloudNames.ALIYUN


def identify_aws(data):
    # data is a dictionary returned by _collect_platform_data.
    uuid_str = data["uuid"]
    if uuid_str.startswith("ec2"):
        # example same-endian uuid:
        # EC2E1916-9099-7CAF-FD21-012345ABCDEF
        return CloudNames.AWS
    with suppress(ValueError):
        if uuid.UUID(uuid_str).bytes_le.hex().startswith("ec2"):
            # check for other endianness
            # example other-endian uuid:
            # 45E12AEC-DCD1-B213-94ED-012345ABCDEF
            return CloudNames.AWS
    return None


def identify_brightbox(data):
    if data["serial"].endswith(".brightbox.com"):
        return CloudNames.BRIGHTBOX


def identify_zstack(data):
    if data["asset_tag"].endswith(".zstack.io"):
        return CloudNames.ZSTACK


def identify_e24cloud(data):
    if data["vendor"] == "e24cloud":
        return CloudNames.E24CLOUD


def identify_outscale(data):
    if (
        data["product_name"] == "3DS Outscale VM".lower()
        and data["vendor"] == "3DS Outscale".lower()
    ):
        return CloudNames.OUTSCALE


def identify_platform():
    # identify the platform and return an entry in CloudNames.
    data = _collect_platform_data()
    checks = (
        identify_aws,
        identify_brightbox,
        identify_zstack,
        identify_e24cloud,
        identify_outscale,
        identify_aliyun,
        lambda x: CloudNames.UNKNOWN,
    )
    for checker in checks:
        try:
            result = checker(data)
            if result:
                return result
        except Exception as e:
            LOG.warning(
                "calling %s with %s raised exception: %s", checker, data, e
            )


def _collect_platform_data():
    """Returns a dictionary of platform info from dmi or /sys/hypervisor.

    Keys in the dictionary are as follows:
       uuid: system-uuid from dmi or /sys/hypervisor
       serial: dmi 'system-serial-number' (/sys/.../product_serial)
       asset_tag: 'dmidecode -s chassis-asset-tag'
       vendor: dmi 'system-manufacturer' (/sys/.../sys_vendor)
       product_name: dmi 'system-product-name' (/sys/.../system-manufacturer)

    On Ec2 instances experimentation is that product_serial is upper case,
    and product_uuid is lower case.  This returns lower case values for both.
    """
    uuid = None
    with suppress(OSError, UnicodeDecodeError):
        uuid = util.load_text_file("/sys/hypervisor/uuid").strip()

    uuid = uuid or dmi.read_dmi_data("system-uuid") or ""
    serial = dmi.read_dmi_data("system-serial-number") or ""
    asset_tag = dmi.read_dmi_data("chassis-asset-tag") or ""
    vendor = dmi.read_dmi_data("system-manufacturer") or ""
    product_name = dmi.read_dmi_data("system-product-name") or ""

    return {
        "uuid": uuid.lower(),
        "serial": serial.lower(),
        "asset_tag": asset_tag.lower(),
        "vendor": vendor.lower(),
        "product_name": product_name.lower(),
    }


def _build_nic_order(
    macs_metadata: Dict[str, Dict],
    macs_to_nics: Dict[str, str],
    fallback_nic_order: NicOrder = NicOrder.MAC,
) -> Dict[str, int]:
    """
    Builds a dictionary containing macs as keys and nic orders as values,
    taking into account `network-card` and `device-number` if present.

    Note that the first NIC will be the primary NIC as it will be the one with
    [network-card] == 0 and device-number == 0 if present.

    @param macs_metadata: dictionary with mac address as key and contents like:
    {"device-number": "0", "interface-id": "...", "local-ipv4s": ...}
    @macs_to_nics: dictionary with mac address as key and nic name as value

    @return: Dictionary with macs as keys and nic orders as values.
    """
    nic_order: Dict[str, int] = {}
    if len(macs_to_nics) == 0 or len(macs_metadata) == 0:
        return nic_order

    valid_macs_metadata = filter(
        # filter out nics without metadata (not a physical nic)
        lambda mmd: mmd[1] is not None,
        # filter by macs
        map(
            lambda mac: (mac, macs_metadata.get(mac), macs_to_nics[mac]),
            macs_to_nics.keys(),
        ),
    )

    def _get_key_as_int_or(dikt, key, alt_value):
        value = dikt.get(key, None)
        if value is not None:
            return int(value)
        return alt_value

    # Sort by (network_card, device_index) as some instances could have
    # multiple network cards with repeated device indexes.
    #
    # On platforms where network-card and device-number are not present,
    # as AliYun, the order will be by mac, as before the introduction of this
    # function.
    return {
        mac: i
        for i, (mac, _mac_metadata, _nic_name) in enumerate(
            sorted(
                valid_macs_metadata,
                key=lambda mmd: (
                    _get_key_as_int_or(
                        mmd[1], "network-card", float("infinity")
                    ),
                    _get_key_as_int_or(
                        mmd[1], "device-number", float("infinity")
                    ),
                    mmd[2]
                    if fallback_nic_order == NicOrder.NIC_NAME
                    else mmd[0],
                ),
            )
        )
    }


def _configure_policy_routing(
    dev_config: dict,
    *,
    nic_name: str,
    nic_metadata: dict,
    distro: Distro,
    is_ipv4: bool,
    table: int,
) -> None:
    """
    Configure policy-based routing on secondary NICs / secondary IPs to
    ensure outgoing packets are routed via the correct interface.

    @param: dev_config: network cfg v2 to be updated inplace.
    @param: nic_name: nic name. Only used if ipv4.
    @param: nic_metadata: nic metadata from IMDS.
    @param: distro: Instance of Distro. Only used if ipv4.
    @param: is_ipv4: Boolean indicating if we are acting over ipv4 or not.
    @param: table: Routing table id.
    """
    if is_ipv4:
        subnet_prefix_routes = nic_metadata.get("subnet-ipv4-cidr-block")
        ips = nic_metadata.get("local-ipv4s")
    else:
        subnet_prefix_routes = nic_metadata.get("subnet-ipv6-cidr-blocks")
        ips = nic_metadata.get("ipv6s")
    if not (subnet_prefix_routes and ips):
        LOG.debug(
            "Not enough IMDS information to configure policy routing "
            "for IPv%s",
            "4" if is_ipv4 else "6",
        )
        return

    if not dev_config.get("routes"):
        dev_config["routes"] = []
    if is_ipv4:
        try:
            lease = distro.dhcp_client.dhcp_discovery(nic_name, distro=distro)
            gateway = lease["routers"]
        except NoDHCPLeaseError as e:
            LOG.warning(
                "Could not perform dhcp discovery on %s to find its "
                "gateway. Not adding default route via the gateway. "
                "Error: %s",
                nic_name,
                e,
            )
        else:
            # Add default route via the NIC's gateway
            dev_config["routes"].append(
                {
                    "to": "0.0.0.0/0",
                    "via": gateway,
                    "table": table,
                },
            )

    subnet_prefix_routes = (
        [subnet_prefix_routes]
        if isinstance(subnet_prefix_routes, str)
        else subnet_prefix_routes
    )
    for prefix_route in subnet_prefix_routes:
        dev_config["routes"].append(
            {
                "to": prefix_route,
                "table": table,
            },
        )

    if not dev_config.get("routing-policy"):
        dev_config["routing-policy"] = []
    # Packets coming from any IP associated with the current NIC
    # will be routed using `table` routing table
    ips = [ips] if isinstance(ips, str) else ips
    for ip in ips:
        dev_config["routing-policy"].append(
            {
                "from": ip,
                "table": table,
            },
        )


def convert_ec2_metadata_network_config(
    network_md,
    distro,
    macs_to_nics=None,
    fallback_nic=None,
    full_network_config=True,
    fallback_nic_order=NicOrder.MAC,
):
    """Convert ec2 metadata to network config version 2 data dict.

    @param: network_md: 'network' portion of EC2 metadata.
       generally formed as {"interfaces": {"macs": {}} where
       'macs' is a dictionary with mac address as key and contents like:
       {"device-number": "0", "interface-id": "...", "local-ipv4s": ...}
    @param: distro: instance of Distro.
    @param: macs_to_nics: Optional dict of mac addresses and nic names. If
       not provided, get_interfaces_by_mac is called to get it from the OS.
    @param: fallback_nic: Optionally provide the primary nic interface name.
       This nic will be guaranteed to minimally have a dhcp4 configuration.
    @param: full_network_config: Boolean set True to configure all networking
       presented by IMDS. This includes rendering secondary IPv4 and IPv6
       addresses on all NICs and rendering network config on secondary NICs.
       If False, only the primary nic will be configured and only with dhcp
       (IPv4/IPv6).

    @return A dict of network config version 2 based on the metadata and macs.
    """
    netcfg = {"version": 2, "ethernets": {}}
    if not macs_to_nics:
        macs_to_nics = net.get_interfaces_by_mac()
    macs_metadata = network_md["interfaces"]["macs"]

    if not full_network_config:
        for mac, nic_name in macs_to_nics.items():
            if nic_name == fallback_nic:
                break
        dev_config = {
            "dhcp4": True,
            "dhcp6": False,
            "match": {"macaddress": mac.lower()},
            "set-name": nic_name,
        }
        nic_metadata = macs_metadata.get(mac)
        if nic_metadata.get("ipv6s"):  # Any IPv6 addresses configured
            dev_config["dhcp6"] = True
        netcfg["ethernets"][nic_name] = dev_config
        return netcfg
    # Apply network config for all nics and any secondary IPv4/v6 addresses
    is_netplan = isinstance(distro.network_renderer, netplan.Renderer)
    nic_order = _build_nic_order(
        macs_metadata, macs_to_nics, fallback_nic_order
    )
    macs = sorted(macs_to_nics.keys())
    for mac in macs:
        nic_name = macs_to_nics[mac]
        nic_metadata = macs_metadata.get(mac)
        if not nic_metadata:
            continue  # Not a physical nic represented in metadata
        nic_idx = nic_order[mac]
        is_primary_nic = nic_idx == 0
        # nic_idx + 1 to start route_metric at 100 (nic_idx is 0-indexed)
        dhcp_override = {"route-metric": (nic_idx + 1) * 100}
        dev_config = {
            "dhcp4": True,
            "dhcp4-overrides": dhcp_override,
            "dhcp6": False,
            "match": {"macaddress": mac.lower()},
            "set-name": nic_name,
        }
        # This config only works on systems using Netplan because Networking
        # config V2 does not support `routing-policy`, but this config is
        # passed through on systems using Netplan.
        # See: https://github.com/canonical/cloud-init/issues/4862
        #
        # If device-number is not present (AliYun or other ec2-like platforms),
        # do not configure source-routing as we cannot determine which is the
        # primary NIC.
        table = 100 + nic_idx
        if (
            is_netplan
            and nic_metadata.get("device-number")
            and not is_primary_nic
        ):
            dhcp_override["use-routes"] = True
            _configure_policy_routing(
                dev_config,
                distro=distro,
                nic_name=nic_name,
                nic_metadata=nic_metadata,
                is_ipv4=True,
                table=table,
            )
        if nic_metadata.get("ipv6s"):  # Any IPv6 addresses configured
            dev_config["dhcp6"] = True
            dev_config["dhcp6-overrides"] = dhcp_override
            if (
                is_netplan
                and nic_metadata.get("device-number")
                and not is_primary_nic
            ):
                _configure_policy_routing(
                    dev_config,
                    distro=distro,
                    nic_name=nic_name,
                    nic_metadata=nic_metadata,
                    is_ipv4=False,
                    table=table,
                )
        dev_config["addresses"] = get_secondary_addresses(nic_metadata, mac)
        if not dev_config["addresses"]:
            dev_config.pop("addresses")  # Since we found none configured

        netcfg["ethernets"][nic_name] = dev_config
    # Remove route-metric dhcp overrides and routes / routing-policy if only
    # one nic configured
    if len(netcfg["ethernets"]) == 1:
        for nic_name in netcfg["ethernets"].keys():
            netcfg["ethernets"][nic_name].pop("dhcp4-overrides")
            netcfg["ethernets"][nic_name].pop("dhcp6-overrides", None)
            netcfg["ethernets"][nic_name].pop("routes", None)
            netcfg["ethernets"][nic_name].pop("routing-policy", None)
    return netcfg


def get_secondary_addresses(nic_metadata, mac):
    """Parse interface-specific nic metadata and return any secondary IPs

    :return: List of secondary IPv4 or IPv6 addresses to configure on the
    interface
    """
    ipv4s = nic_metadata.get("local-ipv4s")
    ipv6s = nic_metadata.get("ipv6s")
    addresses = []
    # In version < 2018-09-24 local_ipv4s or ipv6s is a str with one IP
    if bool(isinstance(ipv4s, list) and len(ipv4s) > 1):
        addresses.extend(
            _get_secondary_addresses(
                nic_metadata, "subnet-ipv4-cidr-block", mac, ipv4s, "24"
            )
        )
    if bool(isinstance(ipv6s, list) and len(ipv6s) > 1):
        addresses.extend(
            _get_secondary_addresses(
                nic_metadata, "subnet-ipv6-cidr-block", mac, ipv6s, "128"
            )
        )
    return sorted(addresses)


def _get_secondary_addresses(nic_metadata, cidr_key, mac, ips, default_prefix):
    """Return list of IP addresses as CIDRs for secondary IPs

    The CIDR prefix will be default_prefix if cidr_key is absent or not
    parseable in nic_metadata.
    """
    addresses = []
    cidr = nic_metadata.get(cidr_key)
    prefix = default_prefix
    if not cidr or len(cidr.split("/")) != 2:
        ip_type = "ipv4" if "ipv4" in cidr_key else "ipv6"
        LOG.warning(
            "Could not parse %s %s for mac %s. %s network"
            " config prefix defaults to /%s",
            cidr_key,
            cidr,
            mac,
            ip_type,
            prefix,
        )
    else:
        prefix = cidr.split("/")[1]
    # We know we have > 1 ips for in metadata for this IP type
    for ip in ips[1:]:
        addresses.append("{ip}/{prefix}".format(ip=ip, prefix=prefix))
    return addresses


# Used to match classes to dependencies
datasources = [
    (DataSourceEc2Local, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceEc2, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
