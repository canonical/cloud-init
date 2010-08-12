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

import cloudinit
import UserDataHandler as ud

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
