# vi: ts=4 expandtab
#
#    Copyright (C) 2009-2010 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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


DEP_FILESYSTEM = "FILESYSTEM"
DEP_NETWORK = "NETWORK"

import UserDataHandler as ud

log = None
def setlog(log_in=None, name="DataSource"):
    log = log_in
    if log is None:
        class NullHandler(logging.Handler):
            def emit(self,record): pass
        log = logging.getLogger(name)
        log.addHandler(NullHandler())

class DataSource:
    userdata = None
    metadata = None
    userdata_raw = None

    def __init__(self):
        pass

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
        return({ })

    def get_public_ssh_keys(self):
        keys = []
        if not self.metadata.has_key('public-keys'): return([])
        for keyname, klist in self.metadata['public-keys'].items():
            # lp:506332 uec metadata service responds with
            # data that makes boto populate a string for 'klist' rather
            # than a list.
            if isinstance(klist,str):
                klist = [ klist ]
            for pkey in klist:
                # there is an empty string at the end of the keylist, trim it
                if pkey:
                    keys.append(pkey)

        return(keys)

    def device_name_to_device(self, name):
        # translate a 'name' to a device
        # the primary function at this point is on ec2
        # to consult metadata service, that has
        #  ephemeral0: sdb
        # and return 'sdb' for input 'ephemeral0'
        return(None)

    def get_locale(self):
        return('en_US.UTF-8')

    def get_local_mirror(self):
        return('http://archive.ubuntu.com/ubuntu/')

    def get_instance_id(self):
        if 'instance-id' not in self.metadata:
            return "ubuntuhost"
        return(self.metadata['instance-id'])

    def get_hostname(self):
        if not 'local-hostname' in self.metadata:
            return None

        toks = self.metadata['local-hostname'].split('.')
        # if there is an ipv4 address in 'local-hostname', then
        # make up a hostname (LP: #475354)
        if len(toks) == 4:
            try:
                r = filter(lambda x: int(x) < 256 and x > 0, toks)
                if len(r) == 4:
                    return("ip-%s" % '-'.join(r))
            except: pass
        return toks[0]

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
def list_sources(cfg_list, depends, pkglist=[]):
    retlist = []
    for ds_coll in cfg_list:
        for pkg in pkglist:
            if pkg: pkg="%s." % pkg
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
    retlist = [ ]
    depset = set(depends)
    for elem in dslist:
        (cls, deps) = elem
        if depset == set(deps):
            retlist.append(cls)
    return(retlist)
