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
import textwrap
import time

from cloudinit import ec2_utils as ec2
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper as uhelp
from cloudinit import util

LOG = logging.getLogger(__name__)

# Which version we are requesting of the ec2 metadata apis
DEF_MD_VERSION = '2009-04-04'

STRICT_ID_PATH = ("datasource", "Ec2", "strict_id")
STRICT_ID_DEFAULT = "warn"


class Platforms(object):
    ALIYUN = "AliYun"
    AWS = "AWS"
    SEEDED = "Seeded"
    UNKNOWN = "Unknown"


class DataSourceEc2(sources.DataSource):
    # Default metadata urls that will be used if none are provided
    # They will be checked for 'resolveability' and some of the
    # following may be discarded if they do not resolve
    metadata_urls = ["http://169.254.169.254", "http://instance-data.:8773"]
    _cloud_platform = None

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        self.metadata_address = None
        self.seed_dir = os.path.join(paths.seed_dir, "ec2")
        self.api_ver = DEF_MD_VERSION

    def get_data(self):
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

        try:
            if not self.wait_for_metadata_service():
                return False
            start_time = time.time()
            self.userdata_raw = \
                ec2.get_instance_userdata(self.api_ver, self.metadata_address)
            self.metadata = ec2.get_instance_metadata(self.api_ver,
                                                      self.metadata_address)
            LOG.debug("Crawl of metadata service took %.3f seconds",
                      time.time() - start_time)
            return True
        except Exception:
            util.logexc(LOG, "Failed reading from metadata address %s",
                        self.metadata_address)
            return False

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        return self.metadata.get('ami-launch-index')

    def get_instance_id(self):
        return self.metadata['instance-id']

    def _get_url_settings(self):
        mcfg = self.ds_cfg
        max_wait = 120
        try:
            max_wait = int(mcfg.get("max_wait", max_wait))
        except Exception:
            util.logexc(LOG, "Failed to get max wait. using %s", max_wait)

        timeout = 50
        try:
            timeout = max(0, int(mcfg.get("timeout", timeout)))
        except Exception:
            util.logexc(LOG, "Failed to get timeout, using %s", timeout)

        return (max_wait, timeout)

    def wait_for_metadata_service(self):
        mcfg = self.ds_cfg

        (max_wait, timeout) = self._get_url_settings()
        if max_wait <= 0:
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
            LOG.warn("Empty metadata url list! using default list")
            mdurls = self.metadata_urls

        urls = []
        url2base = {}
        for url in mdurls:
            cur = "%s/%s/meta-data/instance-id" % (url, self.api_ver)
            urls.append(cur)
            url2base[cur] = url

        start_time = time.time()
        url = uhelp.wait_for_url(urls=urls, max_wait=max_wait,
                                 timeout=timeout, status_cb=LOG.warn)

        if url:
            LOG.debug("Using metadata source: '%s'", url2base[url])
        else:
            LOG.critical("Giving up on md from %s after %s seconds",
                         urls, int(time.time() - start_time))

        self.metadata_address = url2base.get(url)
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
            return self.metadata['placement']['availability-zone']
        except KeyError:
            return None

    @property
    def region(self):
        az = self.availability_zone
        if az is not None:
            return az[:-1]
        return None

    @property
    def cloud_platform(self):
        if self._cloud_platform is None:
            self._cloud_platform = identify_platform()
        return self._cloud_platform

    def activate(self, cfg, is_new_instance):
        if not is_new_instance:
            return
        if self.cloud_platform == Platforms.UNKNOWN:
            warn_if_necessary(
                util.get_cfg_by_path(cfg, STRICT_ID_PATH, STRICT_ID_DEFAULT))


def read_strict_mode(cfgval, default):
    try:
        return parse_strict_mode(cfgval)
    except ValueError as e:
        LOG.warn(e)
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


def warn_if_necessary(cfgval):
    try:
        mode, sleep = parse_strict_mode(cfgval)
    except ValueError as e:
        LOG.warn(e)
        return

    if mode == "false":
        return

    show_warning(sleep)


def show_warning(sleep):
    message = textwrap.dedent("""
        ****************************************************************
        # This system is using the EC2 Metadata Service, but does not  #
        # appear to be running on Amazon EC2 or one of cloud-init's    #
        # known platforms that provide a EC2 Metadata service. In the  #
        # future, cloud-init may stop reading metadata from the EC2    #
        # Metadata Service unless the platform can be identified       #
        #                                                              #
        # If you are seeing this message, please file a bug against    #
        # cloud-init at https://bugs.launchpad.net/cloud-init/+filebug #
        # Make sure to include the cloud provider your instance is     #
        # running on.                                                  #
        #                                                              #
        # For more information see                                     #
        #   https://bugs.launchpad.net/cloud-init/+bug/1660385         #
        #                                                              #
        # After you have filed a bug, you can disable this warning by  #
        # launching your instance with the cloud-config below, or      #
        # putting that content into                                    #
        #    /etc/cloud/cloud.cfg.d/99-ec2-datasource.cfg              #
        #                                                              #
        # #cloud-config                                                #
        # datasource:                                                  #
        #  Ec2:                                                        #
        #   strict_id: false                                           #
        #                                                              #
        """)
    closemsg = ""
    if sleep:
        closemsg = "  [sleeping for %d seconds]  " % sleep
    message += closemsg.center(64, "*")
    print(message)
    LOG.warn(message)
    if sleep:
        time.sleep(sleep)


def identify_aws(data):
    # data is a dictionary returned by _collect_platform_data.
    if (data['uuid'].startswith('ec2') and
            (data['uuid_source'] == 'hypervisor' or
             data['uuid'] == data['serial'])):
            return Platforms.AWS

    return None


def identify_platform():
    # identify the platform and return an entry in Platforms.
    data = _collect_platform_data()
    checks = (identify_aws, lambda x: Platforms.UNKNOWN)
    for checker in checks:
        try:
            result = checker(data)
            if result:
                return result
        except Exception as e:
            LOG.warn("calling %s with %s raised exception: %s",
                     checker, data, e)


def _collect_platform_data():
    # returns a dictionary with all lower case values:
    #   uuid: system-uuid from dmi or /sys/hypervisor
    #   uuid_source: 'hypervisor' (/sys/hypervisor/uuid) or 'dmi'
    #   serial: dmi 'system-serial-number' (/sys/.../product_serial)
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


# Used to match classes to dependencies
datasources = [
    (DataSourceEc2, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)

# vi: ts=4 expandtab
