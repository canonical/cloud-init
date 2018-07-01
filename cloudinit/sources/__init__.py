# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import abc
from collections import namedtuple
import copy
import json
import os
import six

from cloudinit.atomic_helper import write_json
from cloudinit import importer
from cloudinit import log as logging
from cloudinit import net
from cloudinit.event import EventType
from cloudinit import type_utils
from cloudinit import user_data as ud
from cloudinit import util

from cloudinit.filters import launch_index
from cloudinit.reporting import events

DSMODE_DISABLED = "disabled"
DSMODE_LOCAL = "local"
DSMODE_NETWORK = "net"
DSMODE_PASS = "pass"

VALID_DSMODES = [DSMODE_DISABLED, DSMODE_LOCAL, DSMODE_NETWORK]

DEP_FILESYSTEM = "FILESYSTEM"
DEP_NETWORK = "NETWORK"
DS_PREFIX = 'DataSource'

# File in which instance meta-data, user-data and vendor-data is written
INSTANCE_JSON_FILE = 'instance-data.json'

# Key which can be provide a cloud's official product name to cloud-init
METADATA_CLOUD_NAME_KEY = 'cloud-name'

UNSET = "_unset"

LOG = logging.getLogger(__name__)


class DataSourceNotFoundException(Exception):
    pass


class InvalidMetaDataException(Exception):
    """Raised when metadata is broken, unavailable or disabled."""
    pass


def process_base64_metadata(metadata, key_path=''):
    """Strip ci-b64 prefix and return metadata with base64-encoded-keys set."""
    md_copy = copy.deepcopy(metadata)
    md_copy['base64-encoded-keys'] = []
    for key, val in metadata.items():
        if key_path:
            sub_key_path = key_path + '/' + key
        else:
            sub_key_path = key
        if isinstance(val, str) and val.startswith('ci-b64:'):
            md_copy['base64-encoded-keys'].append(sub_key_path)
            md_copy[key] = val.replace('ci-b64:', '')
        if isinstance(val, dict):
            return_val = process_base64_metadata(val, sub_key_path)
            md_copy['base64-encoded-keys'].extend(
                return_val.pop('base64-encoded-keys'))
            md_copy[key] = return_val
    return md_copy


URLParams = namedtuple(
    'URLParms', ['max_wait_seconds', 'timeout_seconds', 'num_retries'])


@six.add_metaclass(abc.ABCMeta)
class DataSource(object):

    dsmode = DSMODE_NETWORK
    default_locale = 'en_US.UTF-8'

    # Datasource name needs to be set by subclasses to determine which
    # cloud-config datasource key is loaded
    dsname = '_undef'

    # Cached cloud_name as determined by _get_cloud_name
    _cloud_name = None

    # Track the discovered fallback nic for use in configuration generation.
    _fallback_interface = None

    # read_url_params
    url_max_wait = -1   # max_wait < 0 means do not wait
    url_timeout = 10    # timeout for each metadata url read attempt
    url_retries = 5     # number of times to retry url upon 404

    # The datasource defines a list of supported EventTypes during which
    # the datasource can react to changes in metadata and regenerate
    # network configuration on metadata changes.
    # A datasource which supports writing network config on each system boot
    # would set update_events = {'network': [EventType.BOOT]}

    # Default: generate network config on new instance id (first boot).
    update_events = {'network': [EventType.BOOT_NEW_INSTANCE]}

    # N-tuple listing default values for any metadata-related class
    # attributes cached on an instance by a process_data runs. These attribute
    # values are reset via clear_cached_attrs during any update_metadata call.
    cached_attr_defaults = (
        ('ec2_metadata', UNSET), ('network_json', UNSET),
        ('metadata', {}), ('userdata', None), ('userdata_raw', None),
        ('vendordata', None), ('vendordata_raw', None))

    _dirty_cache = False

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        self.sys_cfg = sys_cfg
        self.distro = distro
        self.paths = paths
        self.userdata = None
        self.metadata = {}
        self.userdata_raw = None
        self.vendordata = None
        self.vendordata_raw = None

        self.ds_cfg = util.get_cfg_by_path(
            self.sys_cfg, ("datasource", self.dsname), {})
        if not self.ds_cfg:
            self.ds_cfg = {}

        if not ud_proc:
            self.ud_proc = ud.UserDataProcessor(self.paths)
        else:
            self.ud_proc = ud_proc

    def __str__(self):
        return type_utils.obj_name(self)

    def _get_standardized_metadata(self):
        """Return a dictionary of standardized metadata keys."""
        return {'v1': {
            'local-hostname': self.get_hostname(),
            'instance-id': self.get_instance_id(),
            'cloud-name': self.cloud_name,
            'region': self.region,
            'availability-zone': self.availability_zone}}

    def clear_cached_attrs(self, attr_defaults=()):
        """Reset any cached metadata attributes to datasource defaults.

        @param attr_defaults: Optional tuple of (attr, value) pairs to
           set instead of cached_attr_defaults.
        """
        if not self._dirty_cache:
            return
        if attr_defaults:
            attr_values = attr_defaults
        else:
            attr_values = self.cached_attr_defaults

        for attribute, value in attr_values:
            if hasattr(self, attribute):
                setattr(self, attribute, value)
        if not attr_defaults:
            self._dirty_cache = False

    def get_data(self):
        """Datasources implement _get_data to setup metadata and userdata_raw.

        Minimally, the datasource should return a boolean True on success.
        """
        self._dirty_cache = True
        return_value = self._get_data()
        json_file = os.path.join(self.paths.run_dir, INSTANCE_JSON_FILE)
        if not return_value:
            return return_value

        instance_data = {
            'ds': {
                'meta-data': self.metadata,
                'user-data': self.get_userdata_raw(),
                'vendor-data': self.get_vendordata_raw()}}
        if hasattr(self, 'network_json'):
            network_json = getattr(self, 'network_json')
            if network_json != UNSET:
                instance_data['ds']['network_json'] = network_json
        if hasattr(self, 'ec2_metadata'):
            ec2_metadata = getattr(self, 'ec2_metadata')
            if ec2_metadata != UNSET:
                instance_data['ds']['ec2_metadata'] = ec2_metadata
        instance_data.update(
            self._get_standardized_metadata())
        try:
            # Process content base64encoding unserializable values
            content = util.json_dumps(instance_data)
            # Strip base64: prefix and return base64-encoded-keys
            processed_data = process_base64_metadata(json.loads(content))
        except TypeError as e:
            LOG.warning('Error persisting instance-data.json: %s', str(e))
            return return_value
        except UnicodeDecodeError as e:
            LOG.warning('Error persisting instance-data.json: %s', str(e))
            return return_value
        write_json(json_file, processed_data, mode=0o600)
        return return_value

    def _get_data(self):
        """Walk metadata sources, process crawled data and save attributes."""
        raise NotImplementedError(
            'Subclasses of DataSource must implement _get_data which'
            ' sets self.metadata, vendordata_raw and userdata_raw.')

    def get_url_params(self):
        """Return the Datasource's prefered url_read parameters.

        Subclasses may override url_max_wait, url_timeout, url_retries.

        @return: A URLParams object with max_wait_seconds, timeout_seconds,
            num_retries.
        """
        max_wait = self.url_max_wait
        try:
            max_wait = int(self.ds_cfg.get("max_wait", self.url_max_wait))
        except ValueError:
            util.logexc(
                LOG, "Config max_wait '%s' is not an int, using default '%s'",
                self.ds_cfg.get("max_wait"), max_wait)

        timeout = self.url_timeout
        try:
            timeout = max(
                0, int(self.ds_cfg.get("timeout", self.url_timeout)))
        except ValueError:
            timeout = self.url_timeout
            util.logexc(
                LOG, "Config timeout '%s' is not an int, using default '%s'",
                self.ds_cfg.get('timeout'), timeout)

        retries = self.url_retries
        try:
            retries = int(self.ds_cfg.get("retries", self.url_retries))
        except Exception:
            util.logexc(
                LOG, "Config retries '%s' is not an int, using default '%s'",
                self.ds_cfg.get('retries'), retries)

        return URLParams(max_wait, timeout, retries)

    def get_userdata(self, apply_filter=False):
        if self.userdata is None:
            self.userdata = self.ud_proc.process(self.get_userdata_raw())
        if apply_filter:
            return self._filter_xdata(self.userdata)
        return self.userdata

    def get_vendordata(self):
        if self.vendordata is None:
            self.vendordata = self.ud_proc.process(self.get_vendordata_raw())
        return self.vendordata

    @property
    def fallback_interface(self):
        """Determine the network interface used during local network config."""
        if self._fallback_interface is None:
            self._fallback_interface = net.find_fallback_nic()
            if self._fallback_interface is None:
                LOG.warning(
                    "Did not find a fallback interface on %s.",
                    self.cloud_name)
        return self._fallback_interface

    @property
    def cloud_name(self):
        """Return lowercase cloud name as determined by the datasource.

        Datasource can determine or define its own cloud product name in
        metadata.
        """
        if self._cloud_name:
            return self._cloud_name
        if self.metadata and self.metadata.get(METADATA_CLOUD_NAME_KEY):
            cloud_name = self.metadata.get(METADATA_CLOUD_NAME_KEY)
            if isinstance(cloud_name, six.string_types):
                self._cloud_name = cloud_name.lower()
            LOG.debug(
                'Ignoring metadata provided key %s: non-string type %s',
                METADATA_CLOUD_NAME_KEY, type(cloud_name))
        else:
            self._cloud_name = self._get_cloud_name().lower()
        return self._cloud_name

    def _get_cloud_name(self):
        """Return the datasource name as it frequently matches cloud name.

        Should be overridden in subclasses which can run on multiple
        cloud names, such as DatasourceEc2.
        """
        return self.dsname

    @property
    def launch_index(self):
        if not self.metadata:
            return None
        if 'launch-index' in self.metadata:
            return self.metadata['launch-index']
        return None

    def _filter_xdata(self, processed_ud):
        filters = [
            launch_index.Filter(util.safe_int(self.launch_index)),
        ]
        new_ud = processed_ud
        for f in filters:
            new_ud = f.apply(new_ud)
        return new_ud

    @property
    def is_disconnected(self):
        return False

    def get_userdata_raw(self):
        return self.userdata_raw

    def get_vendordata_raw(self):
        return self.vendordata_raw

    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return {}

    def get_public_ssh_keys(self):
        return normalize_pubkey_data(self.metadata.get('public-keys'))

    def _remap_device(self, short_name):
        # LP: #611137
        # the metadata service may believe that devices are named 'sda'
        # when the kernel named them 'vda' or 'xvda'
        # we want to return the correct value for what will actually
        # exist in this instance
        mappings = {"sd": ("vd", "xvd", "vtb")}
        for (nfrom, tlist) in mappings.items():
            if not short_name.startswith(nfrom):
                continue
            for nto in tlist:
                cand = "/dev/%s%s" % (nto, short_name[len(nfrom):])
                if os.path.exists(cand):
                    return cand
        return None

    def device_name_to_device(self, _name):
        # translate a 'name' to a device
        # the primary function at this point is on ec2
        # to consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        return None

    def get_locale(self):
        """Default locale is en_US.UTF-8, but allow distros to override"""
        locale = self.default_locale
        try:
            locale = self.distro.get_locale()
        except NotImplementedError:
            pass
        return locale

    @property
    def availability_zone(self):
        top_level_az = self.metadata.get(
            'availability-zone', self.metadata.get('availability_zone'))
        if top_level_az:
            return top_level_az
        return self.metadata.get('placement', {}).get('availability-zone')

    @property
    def region(self):
        return self.metadata.get('region')

    def get_instance_id(self):
        if not self.metadata or 'instance-id' not in self.metadata:
            # Return a magic not really instance id string
            return "iid-datasource"
        return str(self.metadata['instance-id'])

    def get_hostname(self, fqdn=False, resolve_ip=False, metadata_only=False):
        """Get hostname or fqdn from the datasource. Look it up if desired.

        @param fqdn: Boolean, set True to return hostname with domain.
        @param resolve_ip: Boolean, set True to attempt to resolve an ipv4
            address provided in local-hostname meta-data.
        @param metadata_only: Boolean, set True to avoid looking up hostname
            if meta-data doesn't have local-hostname present.

        @return: hostname or qualified hostname. Optionally return None when
            metadata_only is True and local-hostname data is not available.
        """
        defdomain = "localdomain"
        defhost = "localhost"
        domain = defdomain

        if not self.metadata or 'local-hostname' not in self.metadata:
            if metadata_only:
                return None
            # this is somewhat questionable really.
            # the cloud datasource was asked for a hostname
            # and didn't have one. raising error might be more appropriate
            # but instead, basically look up the existing hostname
            toks = []
            hostname = util.get_hostname()
            hosts_fqdn = util.get_fqdn_from_hosts(hostname)
            if hosts_fqdn and hosts_fqdn.find(".") > 0:
                toks = str(hosts_fqdn).split(".")
            elif hostname and hostname.find(".") > 0:
                toks = str(hostname).split(".")
            elif hostname:
                toks = [hostname, defdomain]
            else:
                toks = [defhost, defdomain]
        else:
            # if there is an ipv4 address in 'local-hostname', then
            # make up a hostname (LP: #475354) in format ip-xx.xx.xx.xx
            lhost = self.metadata['local-hostname']
            if util.is_ipv4(lhost):
                toks = []
                if resolve_ip:
                    toks = util.gethostbyaddr(lhost)

                if toks:
                    toks = str(toks).split('.')
                else:
                    toks = ["ip-%s" % lhost.replace(".", "-")]
            else:
                toks = lhost.split(".")

        if len(toks) > 1:
            hostname = toks[0]
            domain = '.'.join(toks[1:])
        else:
            hostname = toks[0]

        if fqdn and domain != defdomain:
            return "%s.%s" % (hostname, domain)
        else:
            return hostname

    def get_package_mirror_info(self):
        return self.distro.get_package_mirror_info(data_source=self)

    def update_metadata(self, source_event_types):
        """Refresh cached metadata if the datasource supports this event.

        The datasource has a list of update_events which
        trigger refreshing all cached metadata as well as refreshing the
        network configuration.

        @param source_event_types: List of EventTypes which may trigger a
            metadata update.

        @return True if the datasource did successfully update cached metadata
            due to source_event_type.
        """
        supported_events = {}
        for event in source_event_types:
            for update_scope, update_events in self.update_events.items():
                if event in update_events:
                    if not supported_events.get(update_scope):
                        supported_events[update_scope] = []
                    supported_events[update_scope].append(event)
        for scope, matched_events in supported_events.items():
            LOG.debug(
                "Update datasource metadata and %s config due to events: %s",
                scope, ', '.join(matched_events))
            # Each datasource has a cached config property which needs clearing
            # Once cleared that config property will be regenerated from
            # current metadata.
            self.clear_cached_attrs((('_%s_config' % scope, UNSET),))
        if supported_events:
            self.clear_cached_attrs()
            result = self.get_data()
            if result:
                return True
        return False

    def check_instance_id(self, sys_cfg):
        # quickly (local check only) if self.instance_id is still
        return False

    @staticmethod
    def _determine_dsmode(candidates, default=None, valid=None):
        # return the first candidate that is non None, warn if not valid
        if default is None:
            default = DSMODE_NETWORK

        if valid is None:
            valid = VALID_DSMODES

        for candidate in candidates:
            if candidate is None:
                continue
            if candidate in valid:
                return candidate
            else:
                LOG.warning("invalid dsmode '%s', using default=%s",
                            candidate, default)
                return default

        return default

    @property
    def network_config(self):
        return None

    @property
    def first_instance_boot(self):
        return

    def setup(self, is_new_instance):
        """setup(is_new_instance)

        This is called before user-data and vendor-data have been processed.

        Unless the datasource has set mode to 'local', then networking
        per 'fallback' or per 'network_config' will have been written and
        brought up the OS at this point.
        """
        return

    def activate(self, cfg, is_new_instance):
        """activate(cfg, is_new_instance)

        This is called before the init_modules will be called but after
        the user-data and vendor-data have been fully processed.

        The cfg is fully up to date config, it contains a merged view of
           system config, datasource config, user config, vendor config.
        It should be used rather than the sys_cfg passed to __init__.

        is_new_instance is a boolean indicating if this is a new instance.
        """
        return


def normalize_pubkey_data(pubkey_data):
    keys = []

    if not pubkey_data:
        return keys

    if isinstance(pubkey_data, six.string_types):
        return str(pubkey_data).splitlines()

    if isinstance(pubkey_data, (list, set)):
        return list(pubkey_data)

    if isinstance(pubkey_data, (dict)):
        for (_keyname, klist) in pubkey_data.items():
            # lp:506332 uec metadata service responds with
            # data that makes boto populate a string for 'klist' rather
            # than a list.
            if isinstance(klist, six.string_types):
                klist = [klist]
            if isinstance(klist, (list, set)):
                for pkey in klist:
                    # There is an empty string at
                    # the end of the keylist, trim it
                    if pkey:
                        keys.append(pkey)

    return keys


def find_source(sys_cfg, distro, paths, ds_deps, cfg_list, pkg_list, reporter):
    ds_list = list_sources(cfg_list, ds_deps, pkg_list)
    ds_names = [type_utils.obj_name(f) for f in ds_list]
    mode = "network" if DEP_NETWORK in ds_deps else "local"
    LOG.debug("Searching for %s data source in: %s", mode, ds_names)

    for name, cls in zip(ds_names, ds_list):
        myrep = events.ReportEventStack(
            name="search-%s" % name.replace("DataSource", ""),
            description="searching for %s data from %s" % (mode, name),
            message="no %s data found from %s" % (mode, name),
            parent=reporter)
        try:
            with myrep:
                LOG.debug("Seeing if we can get any data from %s", cls)
                s = cls(sys_cfg, distro, paths)
                if s.update_metadata([EventType.BOOT_NEW_INSTANCE]):
                    myrep.message = "found %s data from %s" % (mode, name)
                    return (s, type_utils.obj_name(cls))
        except Exception:
            util.logexc(LOG, "Getting data from %s failed", cls)

    msg = ("Did not find any data source,"
           " searched classes: (%s)") % (", ".join(ds_names))
    raise DataSourceNotFoundException(msg)


# Return a list of classes that have the same depends as 'depends'
# iterate through cfg_list, loading "DataSource*" modules
# and calling their "get_datasource_list".
# Return an ordered list of classes that match (if any)
def list_sources(cfg_list, depends, pkg_list):
    src_list = []
    LOG.debug(("Looking for data source in: %s,"
               " via packages %s that matches dependencies %s"),
              cfg_list, pkg_list, depends)
    for ds_name in cfg_list:
        if not ds_name.startswith(DS_PREFIX):
            ds_name = '%s%s' % (DS_PREFIX, ds_name)
        m_locs, _looked_locs = importer.find_module(ds_name,
                                                    pkg_list,
                                                    ['get_datasource_list'])
        for m_loc in m_locs:
            mod = importer.import_module(m_loc)
            lister = getattr(mod, "get_datasource_list")
            matches = lister(depends)
            if matches:
                src_list.extend(matches)
                break
    return src_list


def instance_id_matches_system_uuid(instance_id, field='system-uuid'):
    # quickly (local check only) if self.instance_id is still valid
    # we check kernel command line or files.
    if not instance_id:
        return False

    dmi_value = util.read_dmi_data(field)
    if not dmi_value:
        return False
    return instance_id.lower() == dmi_value.lower()


def convert_vendordata(data, recurse=True):
    """data: a loaded object (strings, arrays, dicts).
    return something suitable for cloudinit vendordata_raw.

    if data is:
       None: return None
       string: return string
       list: return data
             the list is then processed in UserDataProcessor
       dict: return convert_vendordata(data.get('cloud-init'))
    """
    if not data:
        return None
    if isinstance(data, six.string_types):
        return data
    if isinstance(data, list):
        return copy.deepcopy(data)
    if isinstance(data, dict):
        if recurse is True:
            return convert_vendordata(data.get('cloud-init'),
                                      recurse=False)
        raise ValueError("vendordata['cloud-init'] cannot be dict")
    raise ValueError("Unknown data type for vendordata: %s" % type(data))


# 'depends' is a list of dependencies (DEP_FILESYSTEM)
# ds_list is a list of 2 item lists
# ds_list = [
#   ( class, ( depends-that-this-class-needs ) )
# }
# It returns a list of 'class' that matched these deps exactly
# It mainly is a helper function for DataSourceCollections
def list_from_depends(depends, ds_list):
    ret_list = []
    depset = set(depends)
    for (cls, deps) in ds_list:
        if depset == set(deps):
            ret_list.append(cls)
    return ret_list


# vi: ts=4 expandtab
