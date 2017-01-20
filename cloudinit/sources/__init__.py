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
import copy
import os
import six

from cloudinit import importer
from cloudinit import log as logging
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

LOG = logging.getLogger(__name__)


class DataSourceNotFoundException(Exception):
    pass


@six.add_metaclass(abc.ABCMeta)
class DataSource(object):

    dsmode = DSMODE_NETWORK

    def __init__(self, sys_cfg, distro, paths, ud_proc=None):
        self.sys_cfg = sys_cfg
        self.distro = distro
        self.paths = paths
        self.userdata = None
        self.metadata = None
        self.userdata_raw = None
        self.vendordata = None
        self.vendordata_raw = None

        # find the datasource config name.
        # remove 'DataSource' from classname on front, and remove 'Net' on end.
        # Both Foo and FooNet sources expect config in cfg['sources']['Foo']
        name = type_utils.obj_name(self)
        if name.startswith(DS_PREFIX):
            name = name[len(DS_PREFIX):]
        if name.endswith('Net'):
            name = name[0:-3]

        self.ds_cfg = util.get_cfg_by_path(self.sys_cfg,
                                           ("datasource", name), {})
        if not self.ds_cfg:
            self.ds_cfg = {}

        if not ud_proc:
            self.ud_proc = ud.UserDataProcessor(self.paths)
        else:
            self.ud_proc = ud_proc

    def __str__(self):
        return type_utils.obj_name(self)

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
        return 'en_US.UTF-8'

    @property
    def availability_zone(self):
        return self.metadata.get('availability-zone',
                                 self.metadata.get('availability_zone'))

    @property
    def region(self):
        return self.metadata.get('region')

    def get_instance_id(self):
        if not self.metadata or 'instance-id' not in self.metadata:
            # Return a magic not really instance id string
            return "iid-datasource"
        return str(self.metadata['instance-id'])

    def get_hostname(self, fqdn=False, resolve_ip=False):
        defdomain = "localdomain"
        defhost = "localhost"
        domain = defdomain

        if not self.metadata or 'local-hostname' not in self.metadata:
            # this is somewhat questionable really.
            # the cloud datasource was asked for a hostname
            # and didn't have one. raising error might be more appropriate
            # but instead, basically look up the existing hostname
            toks = []
            hostname = util.get_hostname()
            fqdn = util.get_fqdn_from_hosts(hostname)
            if fqdn and fqdn.find(".") > 0:
                toks = str(fqdn).split(".")
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

        if fqdn:
            return "%s.%s" % (hostname, domain)
        else:
            return hostname

    def get_package_mirror_info(self):
        return self.distro.get_package_mirror_info(data_source=self)

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
                LOG.warn("invalid dsmode '%s', using default=%s",
                         candidate, default)
                return default

        return default

    @property
    def network_config(self):
        return None

    @property
    def first_instance_boot(self):
        return

    def activate(self, cfg, is_new_instance):
        """activate(cfg, is_new_instance)

        This is called before the init_modules will be called.
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
                if s.get_data():
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
    LOG.debug(("Looking for for data source in: %s,"
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
