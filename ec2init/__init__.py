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

import cPickle
import sys
import os.path
import errno
import pwd

datadir = '/var/lib/cloud/data'
semdir = '/var/lib/cloud/sem'
cachedir = datadir + '/cache'
userdata_raw = datadir + '/user-data.txt'
userdata = datadir + '/user-data.txt.i'
user_scripts_dir = datadir + "/scripts"
cloud_config = datadir + '/cloud-config.txt'
data_source_cache = cachedir + '/obj.pkl'
cfg_env_name = "CLOUD_CFG"

import DataSourceEc2
import UserDataHandler

class EC2Init:
    datasource_list = [ DataSourceEc2.DataSourceEc2 ]
    part_handlers = { }
    conffile = '/etc/ec2-init/ec2-config.cfg'

    def __init__(self):
        self.part_handlers = {
            'text/x-shellscript' : self.handle_user_script,
            'text/cloud-config' : self.handle_cloud_config,
            'text/upstart-job' : self.handle_upstart_job,
            'text/part-handler' : self.handle_handler
        }
        
        self.config = ConfigObj(self.conffile)

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

    def get_userdata(self):
        return(self.datasource.get_userdata())

    def update_cache(self):
        self.write_to_cache()
        self.store_userdata()

    def store_userdata(self):
        f = open(userdata_raw,"wb")
        f.write(self.datasource.get_userdata_raw())
        f.close()

        f = open(userdata,"wb")
        f.write(self.get_userdata())
        f.close()

    def get_cfg_option_bool(self, key, default=None):
        val = self.config.get(key, default)
        if val.lower() in ['1', 'on', 'yes']:
            return True
        return False

    def get_cfg_option_str(self, key, default=None):
            return self.config.get(key, default)

    def initctl_emit(self):
        import subprocess
        subprocess.Popen(['initctl', 'emit', 'cloud-config',
            '%s=%s' % (cfg_env_name,cloud_config)]).communicate()

    def sem_getpath(self,name,freq):
        freqtok = freq
        if freq == 'once-per-instance':
            freqtok = self.datasource.get_instance_id()

        return("%s/%s.%s" % (semdir,name,freqtok))
    
    def sem_has_run(self,name,freq):
        semfile = self.sem_getpath(name,freq)
        if os.path.exists(semfile):
            return True
        return False
    
    def sem_acquire(self,name,freq):
        from time import time
        semfile = self.sem_getpath(name,freq)
    
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
            f.write("%s\n" % str(time()))
            f.close()
        except:
            return(False)
        return(True)
    
    def sem_clear(self,name,freq):
        semfile = self.sem_getpath(name,freq)
        try:
            os.unlink(semfile)
        except OSError as e:
            if e.errno != errno.ENOENT:
                return False
            
        return True

    # acquire lock on 'name' for given 'freq'
    # if that does not exist, then call 'func' with given 'args'
    # if 'clear_on_fail' is True and func throws an exception
    #  then remove the lock (so it would run again)
    def sem_and_run(self,semname,freq,func,args=[],clear_on_fail=False):
        if self.sem_has_run(semname,freq): return
        try:
            if not self.sem_acquire(semname,freq):
                raise Exception("Failed to acquire lock on %s\n" % semname)

            func(*args)
        except:
            if clear_on_fail:
                self.sem_clear(semname,freq)
            raise

    def consume_userdata(self):
        self.get_userdata()
        data = self
        # give callbacks opportunity to initialize
        for ctype, func in self.part_handlers.items():
            func(data, "__begin__",None,None)
        UserDataHandler.walk_userdata(self.get_userdata(),
            self.part_handlers, data)

        # give callbacks opportunity to finalize
        for ctype, func in self.part_handlers.items():
            func(data,"__end__",None,None)

    def handle_handler(self,data,ctype,filename,payload):
        if ctype == "__begin__" or ctype == "__end__": return

        # - do something to include the handler, ie, eval it or something
        # - call it with '__begin__'
        # - add it self.part_handlers
        # self.part_handlers['new_type']=handler
        print "Do not know what to do with a handler yet, sorry"

    def handle_user_script(self,data,ctype,filename,payload):
        if ctype == "__end__": return
        if ctype == "__begin__":
            # maybe delete existing things here
            return

        filename=filename.replace(os.sep,'_')
        write_file("%s/%s" % (user_scripts_dir,filename), payload, 0700)

    def handle_upstart_job(self,data,ctype,filename,payload):
        if ctype == "__end__" or ctype == "__begin__": return
        if not filename.endswith(".conf"):
            filename=filename+".conf"

        write_file("%s/%s" % ("/etc/init",filename), payload, 0644)

    def handle_cloud_config(self,data,ctype,filename,payload):
        if ctype == "__begin__":
            self.cloud_config_str=""
            return
        if ctype == "__end__":
            f=open(cloud_config, "wb")
            f.write(self.cloud_config_str)
            f.close()
            return

        self.cloud_config_str+="\n#%s\n%s" % (filename,payload)

    def get_public_ssh_keys(self):
        return(self.datasource.get_public_ssh_keys())

    def get_locale(self):
        return(self.datasource.get_locale())

    def get_mirror(self):
        return(self.datasource.get_local_mirror())

    def get_hostname(self):
        return(self.datasource.get_hostname())

    def apply_credentials(self):
        user = self.get_cfg_option_str('user')
        disable_root = self.get_cfg_option_bool('disable_root', True)
        
        keys = self.get_public_ssh_keys()

        if user:
            setup_user_keys(keys, user, '')
     
        if disable_root:
            key_prefix = 'command="echo \'Please login as the ubuntu user rather than root user.\';echo;sleep 10" ' 
        else:
            key_prefix = ''

        setup_user_keys(keys, 'root', key_prefix)


def write_file(file,content,mode=0644):
        try:
            os.makedirs(os.path.dirname(file))
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise e

        f=open(file,"wb")
        f.write(content)
        f.close()
        os.chmod(file,mode)

def setup_user_keys(keys, user, key_prefix):
    saved_umask = os.umask(077)

    pwent = pwd.getpwnam(user)

    ssh_dir = '%s/.ssh' % pwent.pw_dir
    if not os.path.exists(ssh_dir):
        os.mkdir(ssh_dir)
        os.chown(ssh_dir, pwent.pw_uid, pwent.pw_gid)

    authorized_keys = '%s/.ssh/authorized_keys' % pwent.pw_dir
    fp = open(authorized_keys, 'a')
    fp.write(''.join(['%s%s\n' % (key_prefix, key) for key in keys]))
    fp.close()

    os.chown(authorized_keys, pwent.pw_uid, pwent.pw_gid)

    os.umask(saved_umask)

