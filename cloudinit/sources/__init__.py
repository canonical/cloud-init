# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#    Copyright (C) 2012 Yahoo! Inc.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#    Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import user_data as ud
from cloudinit import util

DEP_FILESYSTEM = "FILESYSTEM"
DEP_NETWORK = "NETWORK"
DS_PREFIX = 'DataSource'

LOG = logging.getLogger(__name__)


class DataSourceNotFoundException(Exception):
    pass


class DataSource(object):
    def __init__(self, sys_cfg, distro, paths):
        self.sys_cfg = sys_cfg
        self.distro = distro
        self.paths = paths
        self.userdata = None
        self.metadata = None
        self.userdata_raw = None
        name = util.obj_name(self)
        if name.startswith(DS_PREFIX):
            name = name[DS_PREFIX:]
        self.ds_cfg = util.get_cfg_by_path(self.sys_cfg,
                                          ("datasource", name), {})

    def get_userdata(self):
        if self.userdata is None:
            raw_data = self.get_userdata_raw()
            self.userdata = ud.UserDataProcessor(self.paths).process(raw_data)
        return self.userdata

    def get_userdata_raw(self):
        return self.userdata_raw

    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return {}

    def get_public_ssh_keys(self):
        keys = []

        if not self.metadata or 'public-keys' not in self.metadata:
            return keys

        if isinstance(self.metadata['public-keys'], (basestring, str)):
            return str(self.metadata['public-keys']).splitlines()

        if isinstance(self.metadata['public-keys'], (list, set)):
            return list(self.metadata['public-keys'])

        if isinstance(self.metadata['public-keys'], (dict)):
            for _keyname, klist in self.metadata['public-keys'].items():
                # lp:506332 uec metadata service responds with
                # data that makes boto populate a string for 'klist' rather
                # than a list.
                if isinstance(klist, (str, basestring)):
                    klist = [klist]
                if isinstance(klist, (list, set)):
                    for pkey in klist:
                        # There is an empty string at
                        # the end of the keylist, trim it
                        if pkey:
                            keys.append(pkey)

        return keys

    def device_name_to_device(self, _name):
        # translate a 'name' to a device
        # the primary function at this point is on ec2
        # to consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        return None

    def get_locale(self):
        return 'en_US.UTF-8'

    def get_local_mirror(self):
        # ??
        return None

    def get_instance_id(self):
        if not self.metadata or 'instance-id' not in self.metadata:
            # Return a magic not really instance id string
            return "iid-datasource"
        return str(self.metadata['instance-id'])

    def get_hostname(self, fqdn=False):
        defdomain = "localdomain"
        defhost = "localhost"
        domain = defdomain

        if not self.metadata or not 'local-hostname' in self.metadata:
            # this is somewhat questionable really.
            # the cloud datasource was asked for a hostname
            # and didn't have one. raising error might be more appropriate
            # but instead, basically look up the existing hostname
            toks = []
            hostname = util.get_hostname()
            fqdn = util.get_fqdn_from_hosts(hostname)
            if fqdn and fqdn.find(".") > 0:
                toks = str(fqdn).split(".")
            elif hostname:
                toks = [hostname, defdomain]
            else:
                toks = [defhost, defdomain]
        else:
            # if there is an ipv4 address in 'local-hostname', then
            # make up a hostname (LP: #475354) in format ip-xx.xx.xx.xx
            lhost = self.metadata['local-hostname']
            if util.is_ipv4(lhost):
                toks = "ip-%s" % lhost.replace(".", "-")
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


def find_source(sys_cfg, distro, paths, ds_deps, cfg_list, pkg_list):
    ds_list = list_sources(cfg_list, ds_deps, pkg_list)
    ds_names = [util.obj_name(f) for f in ds_list]
    LOG.info("Searching for data source in: %s", ds_names)

    for cls in ds_list:
        ds = util.obj_name(cls)
        try:
            s = cls(distro, sys_cfg, paths)
            if s.get_data():
                return (s, ds)
        except Exception:
            util.logexc(LOG, "Getting data from %s failed", ds)

    msg = "Did not find any data source, searched classes: %s" % (ds_names)
    raise DataSourceNotFoundException(msg)


# return a list of classes that have the same depends as 'depends'
# iterate through cfg_list, loading "DataSourceCollections" modules
# and calling their "get_datasource_list".
# return an ordered list of classes that match
def list_sources(cfg_list, depends, pkg_list):
    src_list = []
    LOG.info(("Looking for for data source in: %s,"
              " %s that matches %s"), cfg_list, pkg_list, depends)
    for ds_coll in cfg_list:
        ds_name = str(ds_coll)
        if not ds_name.startswith(DS_PREFIX):
            ds_name = '%s%s' % (DS_PREFIX, ds_name)
        for pkg in pkg_list:
            pkg_name = []
            if pkg:
                pkg_name.append(str(pkg))
            pkg_name.append(ds_name)
            mod = importer.import_module(".".join(pkg_name))
            if pkg:
                mod = getattr(mod, ds_name, None)
            if not mod:
                continue
            lister = getattr(mod, "get_datasource_list", None)
            if not lister:
                continue
            LOG.debug("Seeing if %s matches using function %s", mod, lister)
            cls_matches = lister(depends)
            if not cls_matches:
                continue
            src_list.extend(cls_matches)
            LOG.debug(("Found a match for data source %s"
                       " in %s with matches %s"), ds_name, mod, cls_matches)
            break
    return src_list


# depends is a list of dependencies (DEP_FILESYSTEM)
# dslist is a list of 2 item lists
# dslist = [
#   ( class, ( depends-that-this-class-needs ) )
# }
# it returns a list of 'class' that matched these deps exactly
# it is a helper function for DataSourceCollections
def list_from_depends(depends, dslist):
    ret_list = []
    depset = set(depends)
    for (cls, deps) in dslist:
        if depset == set(deps):
            ret_list.append(cls)
    return ret_list
