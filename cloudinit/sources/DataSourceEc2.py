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

from cloudinit import ec2_utils as ec2
from cloudinit import log as logging
from cloudinit import net
from cloudinit.net.dhcp import EphemeralDHCPv4, NoDHCPLeaseError
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util
from cloudinit import warnings

LOG = logging.getLogger(__name__)

SKIP_METADATA_URL_CODES = frozenset([uhelp.NOT_FOUND])

STRICT_ID_PATH = ("datasource", "Ec2", "strict_id")
STRICT_ID_DEFAULT = "warn"


class Platforms(object):
    # TODO Rename and move to cloudinit.cloud.CloudNames
    ALIYUN = "AliYun"
    AWS = "AWS"
    BRIGHTBOX = "Brightbox"
    SEEDED = "Seeded"
    # UNKNOWN indicates no positive id.  If strict_id is 'warn' or 'false',
    # then an attempt at the Ec2 Metadata service will be made.
    UNKNOWN = "Unknown"
    # NO_EC2_METADATA indicates this platform does not have a Ec2 metadata
    # service available. No attempt at the Ec2 Metadata service will be made.
    NO_EC2_METADATA = "No-EC2-Metadata"


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
    extended_metadata_versions = ['2016-09-02']

    # Setup read_url parameters per get_url_params.
    url_max_wait = 120
    url_timeout = 50

    _cloud_platform = None

    _network_config = sources.UNSET  # Used to cache calculated network cfg v1

    # Whether we want to get network configuration from the metadata service.
    perform_dhcp_setup = False

    def __init__(self, sys_cfg, distro, paths):
        super(DataSourceEc2, self).__init__(sys_cfg, distro, paths)
        self.metadata_address = None
        self.seed_dir = os.path.join(paths.seed_dir, "ec2")

    def _get_cloud_name(self):
        """Return the cloud name as identified during _get_data."""
        return self.cloud_platform

    def _get_data(self):
        seed_ret = {}
        if util.read_optional_seed(seed_ret, base=(self.seed_dir + "/")):
            self.userdata_raw = seed_ret['user-data']
            self.metadata = seed_ret['meta-data']
            LOG.debug("Using seeded ec2 data from %s", self.seed_dir)
            self._cloud_platform = Platforms.SEEDED
            return True

        strict_mode, _sleep = read_strict_mode(
            util.get_cfg_by_path(self.sys_cfg, STRICT_ID_PATH,
                                 STRICT_ID_DEFAULT), ("warn", None))

        LOG.debug("strict_mode: %s, cloud_platform=%s",
                  strict_mode, self.cloud_platform)
        if strict_mode == "true" and self.cloud_platform == Platforms.UNKNOWN:
            return False
        elif self.cloud_platform == Platforms.NO_EC2_METADATA:
            return False

        if self.perform_dhcp_setup:  # Setup networking in init-local stage.
            if util.is_FreeBSD():
                LOG.debug("FreeBSD doesn't support running dhclient with -sf")
                return False
            try:
                with EphemeralDHCPv4(self.fallback_interface):
                    return util.log_time(
                        logfunc=LOG.debug, msg='Crawl of metadata service',
                        func=self._crawl_metadata)
            except NoDHCPLeaseError:
                return False
        else:
            return self._crawl_metadata()

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        return self.metadata.get('ami-launch-index')

    def get_metadata_api_version(self):
        """Get the best supported api version from the metadata service.

        Loop through all extended support metadata versions in order and
        return the most-fully featured metadata api version discovered.

        If extended_metadata_versions aren't present, return the datasource's
        min_metadata_version.
        """
        # Assumes metadata service is already up
        for api_ver in self.extended_metadata_versions:
            url = '{0}/{1}/meta-data/instance-id'.format(
                self.metadata_address, api_ver)
            try:
                resp = uhelp.readurl(url=url)
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
        if self.cloud_platform == Platforms.AWS:
            # Prefer the ID from the instance identity document, but fall back
            if not getattr(self, 'identity', None):
                # If re-using cached datasource, it's get_data run didn't
                # setup self.identity. So we need to do that now.
                api_version = self.get_metadata_api_version()
                self.identity = ec2.get_instance_identity(
                    api_version, self.metadata_address).get('document', {})
            return self.identity.get(
                'instanceId', self.metadata['instance-id'])
        else:
            return self.metadata['instance-id']

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

        urls = []
        url2base = {}
        for url in mdurls:
            cur = '{0}/{1}/meta-data/instance-id'.format(
                url, self.min_metadata_version)
            urls.append(cur)
            url2base[cur] = url

        start_time = time.time()
        url = uhelp.wait_for_url(
            urls=urls, max_wait=url_params.max_wait_seconds,
            timeout=url_params.timeout_seconds, status_cb=LOG.warn)

        if url:
            self.metadata_address = url2base[url]
            LOG.debug("Using metadata source: '%s'", self.metadata_address)
        else:
            LOG.critical("Giving up on md from %s after %s seconds",
                         urls, int(time.time() - start_time))

        return bool(url)

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
            if self.cloud_platform == Platforms.AWS:
                return self.identity.get(
                    'availabilityZone',
                    self.metadata['placement']['availability-zone'])
            else:
                return self.metadata['placement']['availability-zone']
        except KeyError:
            return None

    @property
    def region(self):
        if self.cloud_platform == Platforms.AWS:
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

    @property
    def cloud_platform(self):  # TODO rename cloud_name
        if self._cloud_platform is None:
            self._cloud_platform = identify_platform()
        return self._cloud_platform

    def activate(self, cfg, is_new_instance):
        if not is_new_instance:
            return
        if self.cloud_platform == Platforms.UNKNOWN:
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
            self.cloud_platform == Platforms.AWS)
        if no_network_metadata_on_aws:
            LOG.debug("Metadata 'network' not present:"
                      " Refreshing stale metadata from prior to upgrade.")
            util.log_time(
                logfunc=LOG.debug, msg='Re-crawl of metadata service',
                func=self._crawl_metadata)

        # Limit network configuration to only the primary/fallback nic
        iface = self.fallback_interface
        macs_to_nics = {net.get_interface_mac(iface): iface}
        net_md = self.metadata.get('network')
        if isinstance(net_md, dict):
            result = convert_ec2_metadata_network_config(
                net_md, macs_to_nics=macs_to_nics, fallback_nic=iface)
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

    def _crawl_metadata(self):
        """Crawl metadata service when available.

        @returns: True on success, False otherwise.
        """
        if not self.wait_for_metadata_service():
            return False
        api_version = self.get_metadata_api_version()
        try:
            self.userdata_raw = ec2.get_instance_userdata(
                api_version, self.metadata_address)
            self.metadata = ec2.get_instance_metadata(
                api_version, self.metadata_address)
            if self.cloud_platform == Platforms.AWS:
                self.identity = ec2.get_instance_identity(
                    api_version, self.metadata_address).get('document', {})
        except Exception:
            util.logexc(
                LOG, "Failed reading from metadata address %s",
                self.metadata_address)
            return False
        return True


class DataSourceEc2Local(DataSourceEc2):
    """Datasource run at init-local which sets up network to query metadata.

    In init-local, no network is available. This subclass sets up minimal
    networking with dhclient on a viable nic so that it can talk to the
    metadata service. If the metadata service provides network configuration
    then render the network configuration for that instance based on metadata.
    """
    perform_dhcp_setup = True  # Use dhcp before querying metadata

    def get_data(self):
        supported_platforms = (Platforms.AWS,)
        if self.cloud_platform not in supported_platforms:
            LOG.debug("Local Ec2 mode only supported on %s, not %s",
                      supported_platforms, self.cloud_platform)
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
        except ValueError:
            raise ValueError("Invalid sleep '%s' in strict_id setting '%s': "
                             "not an integer" % (sleep, cfgval))
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
            return Platforms.AWS

    return None


def identify_brightbox(data):
    if data['serial'].endswith('brightbox.com'):
        return Platforms.BRIGHTBOX


def identify_platform():
    # identify the platform and return an entry in Platforms.
    data = _collect_platform_data()
    checks = (identify_aws, identify_brightbox, lambda x: Platforms.UNKNOWN)
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

    On Ec2 instances experimentation is that product_serial is upper case,
    and product_uuid is lower case.  This returns lower case values for both.
    """
    data = {}
    try:
        uuid = util.load_file("/sys/hypervisor/uuid").strip()
        data['uuid_source'] = 'hypervisor'
    except Exception:
        uuid = util.read_dmi_data('system-uuid')
        data['uuid_source'] = 'dmi'

    if uuid is None:
        uuid = ''
    data['uuid'] = uuid.lower()

    serial = util.read_dmi_data('system-serial-number')
    if serial is None:
        serial = ''

    data['serial'] = serial.lower()

    return data


def convert_ec2_metadata_network_config(network_md, macs_to_nics=None,
                                        fallback_nic=None):
    """Convert ec2 metadata to network config version 1 data dict.

    @param: network_md: 'network' portion of EC2 metadata.
       generally formed as {"interfaces": {"macs": {}} where
       'macs' is a dictionary with mac address as key and contents like:
       {"device-number": "0", "interface-id": "...", "local-ipv4s": ...}
    @param: macs_to_nics: Optional dict of mac addresses and nic names. If
       not provided, get_interfaces_by_mac is called to get it from the OS.
    @param: fallback_nic: Optionally provide the primary nic interface name.
       This nic will be guaranteed to minimally have a dhcp4 configuration.

    @return A dict of network config version 1 based on the metadata and macs.
    """
    netcfg = {'version': 1, 'config': []}
    if not macs_to_nics:
        macs_to_nics = net.get_interfaces_by_mac()
    macs_metadata = network_md['interfaces']['macs']
    for mac, nic_name in macs_to_nics.items():
        nic_metadata = macs_metadata.get(mac)
        if not nic_metadata:
            continue  # Not a physical nic represented in metadata
        nic_cfg = {'type': 'physical', 'name': nic_name, 'subnets': []}
        nic_cfg['mac_address'] = mac
        if (nic_name == fallback_nic or nic_metadata.get('public-ipv4s') or
                nic_metadata.get('local-ipv4s')):
            nic_cfg['subnets'].append({'type': 'dhcp4'})
        if nic_metadata.get('ipv6s'):
            nic_cfg['subnets'].append({'type': 'dhcp6'})
        netcfg['config'].append(nic_cfg)
    return netcfg


# Used to match classes to dependencies
datasources = [
    (DataSourceEc2Local, (sources.DEP_FILESYSTEM,)),  # Run at init-local
    (DataSourceEc2, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
