# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Hafliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import time

from cloudinit import dmi
from cloudinit import ec2_utils as ec2
from cloudinit import log as logging
from cloudinit import net
from cloudinit.net.dhcp import EphemeralDHCPv4, NoDHCPLeaseError
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util
from cloudinit import warnings
from cloudinit.event import EventType

LOG = logging.getLogger(__name__)

SKIP_METADATA_URL_CODES = frozenset([uhelp.NOT_FOUND])

STRICT_ID_PATH = ("datasource", "Ec2", "strict_id")
STRICT_ID_DEFAULT = "warn"

API_TOKEN_ROUTE = 'latest/api/token'
AWS_TOKEN_TTL_SECONDS = '21600'
AWS_TOKEN_PUT_HEADER = 'X-aws-ec2-metadata-token'
AWS_TOKEN_REQ_HEADER = AWS_TOKEN_PUT_HEADER + '-ttl-seconds'
AWS_TOKEN_REDACT = [AWS_TOKEN_PUT_HEADER, AWS_TOKEN_REQ_HEADER]


class CloudNames(object):
    ALIYUN = "aliyun"
    AWS = "aws"
    BRIGHTBOX = "brightbox"
    ZSTACK = "zstack"
    E24CLOUD = "e24cloud"
    # UNKNOWN indicates no positive id.  If strict_id is 'warn' or 'false',
    # then an attempt at the Ec2 Metadata service will be made.
    UNKNOWN = "unknown"
    # NO_EC2_METADATA indicates this platform does not have a Ec2 metadata
    # service available. No attempt at the Ec2 Metadata service will be made.
    NO_EC2_METADATA = "no-ec2-metadata"


class DataSourceEc2(sources.DataSource):

    dsname = 'Ec2'
    # Default metadata urls that will be used if none are provided
    # They will be checked for 'resolveability' and some of the
    # following may be discarded if they do not resolve
    metadata_urls = ["http://169.254.169.254", "http://instance-data.:8773"]

    # The minimum supported metadata_version from the ec2 metadata apis
    min_metadata_version = '2009-04-04'

    # Priority ordered list of additional metadata versions which will be tried
    # for extended metadata content. IPv6 support comes in 2016-09-02
    extended_metadata_versions = ['2018-09-24', '2016-09-02']

    # Setup read_url parameters per get_url_params.
    url_max_wait = 120
    url_timeout = 50

    _api_token = None  # API token for accessing the metadata service
    _network_config = sources.UNSET  # Used to cache calculated network cfg v1

    # Whether we want to get network configuration from the metadata service.
    perform_dhcp_setup = False

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceEc2, self).__init__(sys_cfg, distro, paths)
        self.metadata_address = None

    def _get_cloud_name(self):
        """Return the cloud name as identified during _get_data."""
        return identify_platform()

    def _get_data(self):
        strict_mode, _sleep = read_strict_mode(
            util.get_cfg_by_path(self.sys_cfg, STRICT_ID_PATH,
                                 STRICT_ID_DEFAULT), ("warn", None))

        LOG.debug("strict_mode: %s, cloud_name=%s cloud_platform=%s",
                  strict_mode, self.cloud_name, self.platform)
        if strict_mode == "true" and self.cloud_name == CloudNames.UNKNOWN:
            return False
        elif self.cloud_name == CloudNames.NO_EC2_METADATA:
            return False

        if self.perform_dhcp_setup:  # Setup networking in init-local stage.
            if util.is_FreeBSD():
                LOG.debug("FreeBSD doesn't support running dhclient with -sf")
                return False
            try:
                with EphemeralDHCPv4(self.fallback_interface):
                    self._crawled_metadata = util.log_time(
                        logfunc=LOG.debug, msg='Crawl of metadata service',
                        func=self.crawl_metadata)
            except NoDHCPLeaseError:
                return False
        else:
            self._crawled_metadata = util.log_time(
                logfunc=LOG.debug, msg='Crawl of metadata service',
                func=self.crawl_metadata)
        if not self._crawled_metadata:
            return False
        self.metadata = self._crawled_metadata.get('meta-data', None)
        self.userdata_raw = self._crawled_metadata.get('user-data', None)
        self.identity = self._crawled_metadata.get(
            'dynamic', {}).get('instance-identity', {}).get('document', {})
        return True

    def is_classic_instance(self):
        """Report if this instance type is Ec2 Classic (non-vpc)."""
        if not self.metadata:
            # Can return False on inconclusive as we are also called in
            # network_config where metadata will be present.
            # Secondary call site is in packaging postinst script.
            return False
        ifaces_md = self.metadata.get('network', {}).get('interfaces', {})
        for _mac, mac_data in ifaces_md.get('macs', {}).items():
            if 'vpc-id' in mac_data:
                return False
        return True

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        return self.metadata.get('ami-launch-index')

    @property
    def platform(self):
        # Handle upgrade path of pickled ds
        if not hasattr(self, '_platform_type'):
            self._platform_type = DataSourceEc2.dsname.lower()
        if not self._platform_type:
            self._platform_type = DataSourceEc2.dsname.lower()
        return self._platform_type

    def get_metadata_api_version(self):
        """Get the best supported api version from the metadata service.

        Loop through all extended support metadata versions in order and
        return the most-fully featured metadata api version discovered.

        If extended_metadata_versions aren't present, return the datasource's
        min_metadata_version.
        """
        # Assumes metadata service is already up
        url_tmpl = '{0}/{1}/meta-data/instance-id'
        headers = self._get_headers()
        for api_ver in self.extended_metadata_versions:
            url = url_tmpl.format(self.metadata_address, api_ver)
            try:
                resp = uhelp.readurl(url=url, headers=headers,
                                     headers_redact=AWS_TOKEN_REDACT)
            except uhelp.UrlError as e:
                LOG.debug('url %s raised exception %s', url, e)
            else:
                if resp.code == 200:
                    LOG.debug('Found preferred metadata version %s', api_ver)
                    return api_ver
                elif resp.code == 404:
                    msg = 'Metadata api version %s not present. Headers: %s'
                    LOG.debug(msg, api_ver, resp.headers)
        return self.min_metadata_version

    def get_instance_id(self):
        if self.cloud_name == CloudNames.AWS:
            # Prefer the ID from the instance identity document, but fall back
            if not getattr(self, 'identity', None):
                # If re-using cached datasource, it's get_data run didn't
                # setup self.identity. So we need to do that now.
                api_version = self.get_metadata_api_version()
                self.identity = ec2.get_instance_identity(
                    api_version, self.metadata_address,
                    headers_cb=self._get_headers,
                    headers_redact=AWS_TOKEN_REDACT,
                    exception_cb=self._refresh_stale_aws_token_cb).get(
                        'document', {})
            return self.identity.get(
                'instanceId', self.metadata['instance-id'])
        else:
            return self.metadata['instance-id']

    def _maybe_fetch_api_token(self, mdurls, timeout=None, max_wait=None):
        """ Get an API token for EC2 Instance Metadata Service.

        On EC2. IMDS will always answer an API token, unless
        the instance owner has disabled the IMDS HTTP endpoint or
        the network topology conflicts with the configured hop-limit.
        """
        if self.cloud_name != CloudNames.AWS:
            return

        urls = []
        url2base = {}
        url_path = API_TOKEN_ROUTE
        request_method = 'PUT'
        for url in mdurls:
            cur = '{0}/{1}'.format(url, url_path)
            urls.append(cur)
            url2base[cur] = url

        # use the self._imds_exception_cb to check for Read errors
        LOG.debug('Fetching Ec2 IMDSv2 API Token')

        response = None
        url = None
        url_params = self.get_url_params()
        try:
            url, response = uhelp.wait_for_url(
                urls=urls, max_wait=url_params.max_wait_seconds,
                timeout=url_params.timeout_seconds, status_cb=LOG.warning,
                headers_cb=self._get_headers,
                exception_cb=self._imds_exception_cb,
                request_method=request_method,
                headers_redact=AWS_TOKEN_REDACT)
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

        url_params = self.get_url_params()
        if url_params.max_wait_seconds <= 0:
            return False

        # Remove addresses from the list that wont resolve.
        mdurls = mcfg.get("metadata_urls", self.metadata_urls)
        filtered = [x for x in mdurls if util.is_resolvable_url(x)]

        if set(filtered) != set(mdurls):
            LOG.debug("Removed the following from metadata urls: %s",
                      list((set(mdurls) - set(filtered))))

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
        if not metadata_address and self.cloud_name != CloudNames.AWS:
            # if we can't get a token, use instance-id path
            urls = []
            url2base = {}
            url_path = '{ver}/meta-data/instance-id'.format(
                ver=self.min_metadata_version)
            request_method = 'GET'
            for url in mdurls:
                cur = '{0}/{1}'.format(url, url_path)
                urls.append(cur)
                url2base[cur] = url

            start_time = time.time()
            url, _ = uhelp.wait_for_url(
                urls=urls, max_wait=url_params.max_wait_seconds,
                timeout=url_params.timeout_seconds, status_cb=LOG.warning,
                headers_redact=AWS_TOKEN_REDACT, headers_cb=self._get_headers,
                request_method=request_method)

            if url:
                metadata_address = url2base[url]

        if metadata_address:
            self.metadata_address = metadata_address
            LOG.debug("Using metadata source: '%s'", self.metadata_address)
        elif self.cloud_name == CloudNames.AWS:
            LOG.warning("IMDS's HTTP endpoint is probably disabled")
        else:
            LOG.critical("Giving up on md from %s after %s seconds",
                         urls, int(time.time() - start_time))

        return bool(metadata_address)

    def device_name_to_device(self, name):
        # Consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        if 'block-device-mapping' not in self.metadata:
            return None

        # Example:
        # 'block-device-mapping':
        # {'ami': '/dev/sda1',
        # 'ephemeral0': '/dev/sdb',
        # 'root': '/dev/sda1'}
        found = None
        bdm = self.metadata['block-device-mapping']
        if not isinstance(bdm, dict):
            LOG.debug("block-device-mapping not a dictionary: '%s'", bdm)
            return None

        for (entname, device) in bdm.items():
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
                    'availabilityZone',
                    self.metadata['placement']['availability-zone'])
            else:
                return self.metadata['placement']['availability-zone']
        except KeyError:
            return None

    @property
    def region(self):
        if self.cloud_name == CloudNames.AWS:
            region = self.identity.get('region')
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
                cfg)

    @property
    def network_config(self):
        """Return a network config dict for rendering ENI or netplan files."""
        if self._network_config != sources.UNSET:
            return self._network_config

        if self.metadata is None:
            # this would happen if get_data hadn't been called. leave as UNSET
            LOG.warning(
                "Unexpected call to network_config when metadata is None.")
            return None

        result = None
        no_network_metadata_on_aws = bool(
            'network' not in self.metadata and
            self.cloud_name == CloudNames.AWS)
        if no_network_metadata_on_aws:
            LOG.debug("Metadata 'network' not present:"
                      " Refreshing stale metadata from prior to upgrade.")
            util.log_time(
                logfunc=LOG.debug, msg='Re-crawl of metadata service',
                func=self.get_data)

        iface = self.fallback_interface
        net_md = self.metadata.get('network')
        if isinstance(net_md, dict):
            # SRU_BLOCKER: xenial, bionic and eoan should default
            # apply_full_imds_network_config to False to retain original
            # behavior on those releases.
            result = convert_ec2_metadata_network_config(
                net_md, fallback_nic=iface,
                full_network_config=util.get_cfg_option_bool(
                    self.ds_cfg, 'apply_full_imds_network_config', True))

            # RELEASE_BLOCKER: xenial should drop the below if statement,
            # because the issue being addressed doesn't exist pre-netplan.
            # (This datasource doesn't implement check_instance_id() so the
            # datasource object is recreated every boot; this means we don't
            # need to modify update_events on cloud-init upgrade.)

            # Non-VPC (aka Classic) Ec2 instances need to rewrite the
            # network config file every boot due to MAC address change.
            if self.is_classic_instance():
                self.update_events['network'].add(EventType.BOOT)
        else:
            LOG.warning("Metadata 'network' key not valid: %s.", net_md)
        self._network_config = result

        return self._network_config

    @property
    def fallback_interface(self):
        if self._fallback_interface is None:
            # fallback_nic was used at one point, so restored objects may
            # have an attribute there. respect that if found.
            _legacy_fbnic = getattr(self, 'fallback_nic', None)
            if _legacy_fbnic:
                self._fallback_interface = _legacy_fbnic
                self.fallback_nic = None
            else:
                return super(DataSourceEc2, self).fallback_interface
        return self._fallback_interface

    def crawl_metadata(self):
        """Crawl metadata service when available.

        @returns: Dictionary of crawled metadata content containing the keys:
          meta-data, user-data and dynamic.
        """
        if not self.wait_for_metadata_service():
            return {}
        api_version = self.get_metadata_api_version()
        redact = AWS_TOKEN_REDACT
        crawled_metadata = {}
        if self.cloud_name == CloudNames.AWS:
            exc_cb = self._refresh_stale_aws_token_cb
            exc_cb_ud = self._skip_or_refresh_stale_aws_token_cb
        else:
            exc_cb = exc_cb_ud = None
        try:
            crawled_metadata['user-data'] = ec2.get_instance_userdata(
                api_version, self.metadata_address,
                headers_cb=self._get_headers, headers_redact=redact,
                exception_cb=exc_cb_ud)
            crawled_metadata['meta-data'] = ec2.get_instance_metadata(
                api_version, self.metadata_address,
                headers_cb=self._get_headers, headers_redact=redact,
                exception_cb=exc_cb)
            if self.cloud_name == CloudNames.AWS:
                identity = ec2.get_instance_identity(
                    api_version, self.metadata_address,
                    headers_cb=self._get_headers, headers_redact=redact,
                    exception_cb=exc_cb)
                crawled_metadata['dynamic'] = {'instance-identity': identity}
        except Exception:
            util.logexc(
                LOG, "Failed reading from metadata address %s",
                self.metadata_address)
            return {}
        crawled_metadata['_metadata_api_version'] = api_version
        return crawled_metadata

    def _refresh_api_token(self, seconds=AWS_TOKEN_TTL_SECONDS):
        """Request new metadata API token.
        @param seconds: The lifetime of the token in seconds

        @return: The API token or None if unavailable.
        """
        if self.cloud_name != CloudNames.AWS:
            return None
        LOG.debug("Refreshing Ec2 metadata API token")
        request_header = {AWS_TOKEN_REQ_HEADER: seconds}
        token_url = '{}/{}'.format(self.metadata_address, API_TOKEN_ROUTE)
        try:
            response = uhelp.readurl(token_url, headers=request_header,
                                     headers_redact=AWS_TOKEN_REDACT,
                                     request_method="PUT")
        except uhelp.UrlError as e:
            LOG.warning(
                'Unable to get API token: %s raised exception %s',
                token_url, e)
            return None
        return response.contents

    def _skip_or_refresh_stale_aws_token_cb(self, msg, exception):
        """Callback will not retry on SKIP_USERDATA_CODES or if no token
           is available."""
        retry = ec2.skip_retry_on_codes(
            ec2.SKIP_USERDATA_CODES, msg, exception)
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
                    LOG.warning('Ec2 IMDS endpoint returned a 403 error. '
                                'HTTP endpoint is disabled. Aborting.')
                else:
                    LOG.warning('Fatal error while requesting '
                                'Ec2 IMDSv2 API tokens')
                raise exception

    def _get_headers(self, url=''):
        """Return a dict of headers for accessing a url.

        If _api_token is unset on AWS, attempt to refresh the token via a PUT
        and then return the updated token header.
        """
        if self.cloud_name != CloudNames.AWS:
            return {}
        # Request a 6 hour token if URL is API_TOKEN_ROUTE
        request_token_header = {AWS_TOKEN_REQ_HEADER: AWS_TOKEN_TTL_SECONDS}
        if API_TOKEN_ROUTE in url:
            return request_token_header
        if not self._api_token:
            # If we don't yet have an API token, get one via a PUT against
            # API_TOKEN_ROUTE. This _api_token may get unset by a 403 due
            # to an invalid or expired token
            self._api_token = self._refresh_api_token()
            if not self._api_token:
                return {}
        return {AWS_TOKEN_PUT_HEADER: self._api_token}


class DataSourceEc2Local(DataSourceEc2):
    """Datasource run at init-local which sets up network to query metadata.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """
    perform_dhcp_setup = True  # Use dhcp before querying metadata

    def get_data(self):
        supported_platforms = (CloudNames.AWS,)
        if self.cloud_name not in supported_platforms:
            LOG.debug("Local Ec2 mode only supported on %s, not %s",
                      supported_platforms, self.cloud_name)
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
        return 'true', None
    if cfgval is False:
        return 'false', None

    if not cfgval:
        return 'warn', 0

    mode, _, sleep = cfgval.partition(",")
    if mode not in ('true', 'false', 'warn'):
        raise ValueError(
            "Invalid mode '%s' in strict_id setting '%s': "
            "Expected one of 'true', 'false', 'warn'." % (mode, cfgval))

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

    warnings.show_warning('non_ec2_md', cfg, mode=True, sleep=sleep)


def identify_aws(data):
    # data is a dictionary returned by _collect_platform_data.
    if (data['uuid'].startswith('ec2') and
            (data['uuid_source'] == 'hypervisor' or
             data['uuid'] == data['serial'])):
        return CloudNames.AWS

    return None


def identify_brightbox(data):
    if data['serial'].endswith('.brightbox.com'):
        return CloudNames.BRIGHTBOX


def identify_zstack(data):
    if data['asset_tag'].endswith('.zstack.io'):
        return CloudNames.ZSTACK


def identify_e24cloud(data):
    if data['vendor'] == 'e24cloud':
        return CloudNames.E24CLOUD


def identify_platform():
    # identify the platform and return an entry in CloudNames.
    data = _collect_platform_data()
    checks = (identify_aws, identify_brightbox, identify_zstack,
              identify_e24cloud, lambda x: CloudNames.UNKNOWN)
    for checker in checks:
        try:
            result = checker(data)
            if result:
                return result
        except Exception as e:
            LOG.warning("calling %s with %s raised exception: %s",
                        checker, data, e)


def _collect_platform_data():
    """Returns a dictionary of platform info from dmi or /sys/hypervisor.

    Keys in the dictionary are as follows:
       uuid: system-uuid from dmi or /sys/hypervisor
       uuid_source: 'hypervisor' (/sys/hypervisor/uuid) or 'dmi'
       serial: dmi 'system-serial-number' (/sys/.../product_serial)
       asset_tag: 'dmidecode -s chassis-asset-tag'
       vendor: dmi 'system-manufacturer' (/sys/.../sys_vendor)

    On Ec2 instances experimentation is that product_serial is upper case,
    and product_uuid is lower case.  This returns lower case values for both.
    """
    data = {}
    try:
        uuid = util.load_file("/sys/hypervisor/uuid").strip()
        data['uuid_source'] = 'hypervisor'
    except Exception:
        uuid = dmi.read_dmi_data('system-uuid')
        data['uuid_source'] = 'dmi'

    if uuid is None:
        uuid = ''
    data['uuid'] = uuid.lower()

    serial = dmi.read_dmi_data('system-serial-number')
    if serial is None:
        serial = ''

    data['serial'] = serial.lower()

    asset_tag = dmi.read_dmi_data('chassis-asset-tag')
    if asset_tag is None:
        asset_tag = ''

    data['asset_tag'] = asset_tag.lower()

    vendor = dmi.read_dmi_data('system-manufacturer')
    data['vendor'] = (vendor if vendor else '').lower()

    return data


def convert_ec2_metadata_network_config(
        network_md, macs_to_nics=None, fallback_nic=None,
        full_network_config=True):
    """Convert ec2 metadata to network config version 2 data dict.

    @param: network_md: 'network' portion of EC2 metadata.
       generally formed as {"interfaces": {"macs": {}} where
       'macs' is a dictionary with mac address as key and contents like:
       {"device-number": "0", "interface-id": "...", "local-ipv4s": ...}
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
    netcfg = {'version': 2, 'ethernets': {}}
    if not macs_to_nics:
        macs_to_nics = net.get_interfaces_by_mac()
    macs_metadata = network_md['interfaces']['macs']

    if not full_network_config:
        for mac, nic_name in macs_to_nics.items():
            if nic_name == fallback_nic:
                break
        dev_config = {'dhcp4': True,
                      'dhcp6': False,
                      'match': {'macaddress': mac.lower()},
                      'set-name': nic_name}
        nic_metadata = macs_metadata.get(mac)
        if nic_metadata.get('ipv6s'):  # Any IPv6 addresses configured
            dev_config['dhcp6'] = True
        netcfg['ethernets'][nic_name] = dev_config
        return netcfg
    # Apply network config for all nics and any secondary IPv4/v6 addresses
    for mac, nic_name in sorted(macs_to_nics.items()):
        nic_metadata = macs_metadata.get(mac)
        if not nic_metadata:
            continue  # Not a physical nic represented in metadata
        # device-number is zero-indexed, we want it 1-indexed for the
        # multiplication on the following line
        nic_idx = int(nic_metadata['device-number']) + 1
        dhcp_override = {'route-metric': nic_idx * 100}
        dev_config = {'dhcp4': True, 'dhcp4-overrides': dhcp_override,
                      'dhcp6': False,
                      'match': {'macaddress': mac.lower()},
                      'set-name': nic_name}
        if nic_metadata.get('ipv6s'):  # Any IPv6 addresses configured
            dev_config['dhcp6'] = True
            dev_config['dhcp6-overrides'] = dhcp_override
        dev_config['addresses'] = get_secondary_addresses(nic_metadata, mac)
        if not dev_config['addresses']:
            dev_config.pop('addresses')  # Since we found none configured
        netcfg['ethernets'][nic_name] = dev_config
    # Remove route-metric dhcp overrides if only one nic configured
    if len(netcfg['ethernets']) == 1:
        for nic_name in netcfg['ethernets'].keys():
            netcfg['ethernets'][nic_name].pop('dhcp4-overrides')
            netcfg['ethernets'][nic_name].pop('dhcp6-overrides', None)
    return netcfg


def get_secondary_addresses(nic_metadata, mac):
    """Parse interface-specific nic metadata and return any secondary IPs

    :return: List of secondary IPv4 or IPv6 addresses to configure on the
    interface
    """
    ipv4s = nic_metadata.get('local-ipv4s')
    ipv6s = nic_metadata.get('ipv6s')
    addresses = []
    # In version < 2018-09-24 local_ipv4s or ipv6s is a str with one IP
    if bool(isinstance(ipv4s, list) and len(ipv4s) > 1):
        addresses.extend(
            _get_secondary_addresses(
                nic_metadata, 'subnet-ipv4-cidr-block', mac, ipv4s, '24'))
    if bool(isinstance(ipv6s, list) and len(ipv6s) > 1):
        addresses.extend(
            _get_secondary_addresses(
                nic_metadata, 'subnet-ipv6-cidr-block', mac, ipv6s, '128'))
    return sorted(addresses)


def _get_secondary_addresses(nic_metadata, cidr_key, mac, ips, default_prefix):
    """Return list of IP addresses as CIDRs for secondary IPs

    The CIDR prefix will be default_prefix if cidr_key is absent or not
    parseable in nic_metadata.
    """
    addresses = []
    cidr = nic_metadata.get(cidr_key)
    prefix = default_prefix
    if not cidr or len(cidr.split('/')) != 2:
        ip_type = 'ipv4' if 'ipv4' in cidr_key else 'ipv6'
        LOG.warning(
            'Could not parse %s %s for mac %s. %s network'
            ' config prefix defaults to /%s',
            cidr_key, cidr, mac, ip_type, prefix)
    else:
        prefix = cidr.split('/')[1]
    # We know we have > 1 ips for in metadata for this IP type
    for ip in ips[1:]:
        addresses.append(
            '{ip}/{prefix}'.format(ip=ip, prefix=prefix))
    return addresses


# Used to match classes to dependencies
datasources = [
    (DataSourceEc2Local, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceEc2, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
