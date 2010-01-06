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
import cPickle
import sys
import os.path
import errno

datadir = '/var/lib/cloud/data'
semdir = '/var/lib/cloud/sem'
cachedir = datadir + '/cache'
user_data = datadir + '/user-data.txt'
user_data_raw = datadir + '/user-data.raw'
user_config = datadir + '/user-config.txt'
data_source_cache = cachedir + '/obj.pkl'
cfg_env_name = "CLOUD_CFG"

import DataSourceEc2

class EC2Init:
    datasource_list = [ DataSourceEc2.DataSourceEc2 ]

    def restore_from_cache(self):
        try:
            f=open(data_source_cache, "rb")
            data = cPickle.load(f)
            self.datasource = data
            return True
        except:
            return False

    def write_to_cache(self):
        try:
            f=open(data_source_cache, "wb")
            data = cPickle.dump(self.datasource,f)
            return True
        except:
            return False
        
    def get_data_source(self):
        if self.restore_from_cache():
            return True

        for source in self.datasource_list:
            try:
                s = source()
                if s.get_data():
                    self.datasource = s
                    return
            except Exception as e:
                print e
                pass
        raise Exception("Could not find data source")

    def get_user_data(self):
        return(self.datasource.get_user_data())

    def update_cache(self):
        self.write_to_cache()
        self.store_user_data()

    def store_user_data(self):
        f = open(user_data_raw,"wb")
        f.write(self.datasource.get_user_data_raw())
        f.close()

        f = open(user_data,"wb")
        f.write(self.get_user_data())
        f.close()

    def get_cfg_option_bool(self, key, default=None):
        val = self.config.get(key, default)
        if val.lower() in ['1', 'on', 'yes']:
            return True
        return False

    def initctl_emit(self):
        import subprocess
        subprocess.Popen(['initctl', 'emit', 'cloud-config',
            '%s=%s' % (cfg_env_name,user_config)]).communicate()


# if 'str' is compressed return decompressed otherwise return it
def decomp_str(str):
    import StringIO
    import gzip
    try:
        uncomp = gzip.GzipFile(None,"rb",1,StringIO.StringIO(str)).read()
        return(uncomp)
    except:
        return(str)


# preprocess the user data (include / uncompress)
def preprocess_user_data(ud):
    return(decomp_str(ud))

def sem_getpath(name,freq):
    # TODO: freqtok must represent "once-per-instance" somehow
    freqtok = freq
    return("%s/%s.%s" % (semdir,name,freqtok))

def sem_has_run(name,freq):
    semfile = sem_getpath(name,freq)
    if os.path.exists(semfile):
        return True
    return False

def sem_acquire(name,freq):
    from time import time
    semfile = sem_getpath(name,freq)

    try:
        os.makedirs(os.path.dirname(semfile))
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise e

    if os.path.exists(semfile):
        return False

    # race condition
    try:
        f = open(semfile,"w")
        f.write(str(time()))
        f.close()
    except:
        return(False)
    return(True)

def sem_clear(name,freq):
    semfile = sem_getpath(name,freq)
    try:
        os.unlink(semfile)
    except OSError as e:
        if e.errno != errno.ENOENT:
            return False
        
    return True
