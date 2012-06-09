# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Hafliger <juerg.haefliger@hp.com>
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

from cloudinit import user_data as ud
from cloudinit import util

import socket

DEP_FILESYSTEM = "FILESYSTEM"
DEP_NETWORK = "NETWORK"

class DataSourceNotFoundException(Exception):
    pass


class DataSource:
    userdata = None
    metadata = None
    userdata_raw = None
    cfgname = ""
    # system config (passed in from cloudinit,
    # cloud-config before input from the DataSource)
    sys_cfg = {}
    # datasource config, the cloud-config['datasource']['__name__']
    ds_cfg = {}  # datasource config

    def __init__(self, sys_cfg=None):
        if not self.cfgname:
            name = str(self.__class__).split(".")[-1]
            if name.startswith("DataSource"):
                name = name[len("DataSource"):]
            self.cfgname = name
        if sys_cfg:
            self.sys_cfg = sys_cfg

        self.ds_cfg = util.get_cfg_by_path(self.sys_cfg,
                          ("datasource", self.cfgname), self.ds_cfg)

    def get_userdata(self):
        if self.userdata == None:
            self.userdata = ud.preprocess_userdata(self.userdata_raw)
        return self.userdata

    def get_userdata_raw(self):
        return(self.userdata_raw)

    # the data sources' config_obj is a cloud-config formated
    # object that came to it from ways other than cloud-config
    # because cloud-config content would be handled elsewhere
    def get_config_obj(self):
        return({})

    def get_public_ssh_keys(self):
        keys = []
        if 'public-keys' not in self.metadata:
            return([])

        if isinstance(self.metadata['public-keys'], str):
            return(str(self.metadata['public-keys']).splitlines())

        if isinstance(self.metadata['public-keys'], list):
            return(self.metadata['public-keys'])

        for _keyname, klist in self.metadata['public-keys'].items():
            # lp:506332 uec metadata service responds with
            # data that makes boto populate a string for 'klist' rather
            # than a list.
            if isinstance(klist, str):
                klist = [klist]
            for pkey in klist:
                # there is an empty string at the end of the keylist, trim it
                if pkey:
                    keys.append(pkey)

        return(keys)

    def device_name_to_device(self, _name):
        # translate a 'name' to a device
        # the primary function at this point is on ec2
        # to consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        return(None)

    def get_locale(self):
        return('en_US.UTF-8')

    def get_local_mirror(self):
        return None

    def get_instance_id(self):
        if 'instance-id' not in self.metadata:
            return "iid-datasource"
        return(self.metadata['instance-id'])

    def get_hostname(self, fqdn=False):
        defdomain = "localdomain"
        defhost = "localhost"

        domain = defdomain
        if not 'local-hostname' in self.metadata:

            # this is somewhat questionable really.
            # the cloud datasource was asked for a hostname
            # and didn't have one. raising error might be more appropriate
            # but instead, basically look up the existing hostname
            toks = []

            hostname = socket.gethostname()

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
            if is_ipv4(lhost):
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


def find_source(cfg, ds_deps):
    cfglist = cfg.get('datasource_list') or []
    dslist = list_sources(cfglist, ds_deps)
    dsnames = [f.__name__ for f in dslist]
    
    LOG.debug("Searching for data source in %s", dsnames)
    for cls in dslist:
        ds = cls.__name__
        try:
            s = cls(sys_cfg=cfg)
            if s.get_data():
                return (s, ds)
        except Exception as e:
            LOG.exception("Getting data from %s raised %s", ds, e)

    msg = "Did not find any data source, searched classes: %s" % dsnames
    raise DataSourceNotFoundException(msg)


# return a list of classes that have the same depends as 'depends'
# iterate through cfg_list, loading "DataSourceCollections" modules
# and calling their "get_datasource_list".
# return an ordered list of classes that match
#
# - modules must be named "DataSource<item>", where 'item' is an entry
#   in cfg_list
# - if pkglist is given, it will iterate try loading from that package
#   ie, pkglist=[ "foo", "" ]
#     will first try to load foo.DataSource<item>
#     then DataSource<item>
def list_sources(cfg_list, depends, pkglist=None):
    if pkglist is None:
        pkglist = []
    retlist = []
    for ds_coll in cfg_list:
        for pkg in pkglist:
            if pkg:
                pkg = "%s." % pkg
            try:
                mod = __import__("%sDataSource%s" % (pkg, ds_coll))
                if pkg:
                    mod = getattr(mod, "DataSource%s" % ds_coll)
                lister = getattr(mod, "get_datasource_list")
                retlist.extend(lister(depends))
                break
            except:
                raise
    return(retlist)


# depends is a list of dependencies (DEP_FILESYSTEM)
# dslist is a list of 2 item lists
# dslist = [
#   ( class, ( depends-that-this-class-needs ) )
# }
# it returns a list of 'class' that matched these deps exactly
# it is a helper function for DataSourceCollections
def list_from_depends(depends, dslist):
    retlist = []
    depset = set(depends)
    for elem in dslist:
        (cls, deps) = elem
        if depset == set(deps):
            retlist.append(cls)
    return(retlist)
