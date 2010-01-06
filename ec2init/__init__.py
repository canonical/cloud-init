#
#    Common code for the EC2 initialisation scripts in Ubuntu
#    Copyright (C) 2008-2009 Canonical Ltd
#
#    Author: Soren Hansen <soren@canonical.com>
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
#

import os
from   configobj import ConfigObj

import boto.utils

cachedir = '/var/lib/cloud/data/cache'

import DataSourceEc2

class EC2Init:
    datasource_list = [ DataSourceEc2.DataSourceEc2 ]

    def restore_from_cache(self):
        try:
            f=open(cachedir + "/obj.pkl", "rb")
            data = pickle.load(f)
            self.datasource = data
            return True
        except:
            return False

    def write_to_cache(self):
        try:
            f=open(cachedir + "/obj.pkl", "wb")
            data = pickle.dump(self.datasource,f)
            return True
        except:
            return False
        
    def get_data_source(self):
        if self.restore_from_cache():
            return True

        for source in self.datasource_list:
            try:
                print "trying + %s" % source
                s = source()
                if s.get_data():
                    self.datasource = s
                    return
            except:
                pass
        raise Exception("Could not find data source")

    def get_user_data(self):
        return(self.datasource.get_user_data())

    def get_cfg_option_bool(self, key, default=None):
        val = self.config.get(key, default)
        if val.lower() in ['1', 'on', 'yes']:
            return True
        return False

