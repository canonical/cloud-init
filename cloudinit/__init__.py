# vi: ts=4 expandtab
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

datadir = '/var/lib/cloud/data'
semdir = '/var/lib/cloud/sem'
pluginsdir = datadir + '/plugins'
cachedir = datadir + '/cache'
userdata_raw = datadir + '/user-data.txt'
userdata = datadir + '/user-data.txt.i'
user_scripts_dir = datadir + "/scripts"
boothooks_dir = datadir + "/boothooks"
cloud_config = datadir + '/cloud-config.txt'
data_source_cache = cachedir + '/obj.pkl'
system_config = '/etc/cloud/cloud.cfg'
cfg_env_name = "CLOUD_CFG"

def_log_file = '/var/log/cloud-init.log'
cfg_builtin = """
log_cfgs: [ ]
cloud_type: auto
"""
logger_name = "cloudinit"

import os
from   configobj import ConfigObj

import cPickle
import sys
import os.path
import errno
import pwd
import subprocess
import yaml
import util
import logging
import logging.config
import StringIO

class NullHandler(logging.Handler):
	def emit(self,record): pass

log = logging.getLogger(logger_name)
log.addHandler(NullHandler())

def logging_set_from_cfg_file(cfg_file=system_config):
    logging_set_from_cfg(util.get_base_cfg(cfg_file,cfg_builtin))

def logging_set_from_cfg(cfg, logfile=None):
    log_cfgs = []
    logcfg=util.get_cfg_option_str(cfg, "log_cfg", False)
    if logcfg:
        # if there is a 'logcfg' entry in the config, respect
        # it, it is the old keyname
        log_cfgs = [ logcfg ]
    elif "log_cfgs" in cfg:
        for cfg in cfg['log_cfgs']:
            if isinstance(cfg,list):
                log_cfgs.append('\n'.join(cfg))
            else:
                log_cfgs.append()

    if not len(log_cfgs):
        sys.stderr.write("Warning, no logging configured\n")

    for logcfg in log_cfgs:
        try:
            logging.config.fileConfig(StringIO.StringIO(logcfg))
            return
        except:
            pass

    raise Exception("no valid logging found\n")


import DataSourceEc2
import DataSourceNoCloud
import UserDataHandler

class CloudInit:
    datasource_map = {
        "ec2" : DataSourceEc2.DataSourceEc2,
        "nocloud" : DataSourceNoCloud.DataSourceNoCloud,
        "nocloud-net" : DataSourceNoCloud.DataSourceNoCloudNet
    }
    datasource = None
    auto_orders = {
        "all": ( "nocloud-net", "ec2" ),
        "local" : ( "nocloud", ),
    }

    cfg = None
    part_handlers = { }
    old_conffile = '/etc/ec2-init/ec2-config.cfg'
    source_type = "all"

    def __init__(self, source_type = "all", sysconfig=system_config):
        self.part_handlers = {
            'text/x-shellscript' : self.handle_user_script,
            'text/cloud-config' : self.handle_cloud_config,
            'text/upstart-job' : self.handle_upstart_job,
            'text/part-handler' : self.handle_handler,
            'text/cloud-boothook' : self.handle_cloud_boothook
        }
        self.sysconfig=sysconfig
        self.cfg=self.read_cfg()
        self.source_type = source_type

    def read_cfg(self):
        if self.cfg:
            return(self.cfg)

        conf = util.get_base_cfg(self.sysconfig,cfg_builtin)

        # support reading the old ConfigObj format file and merging
        # it into the yaml dictionary
        try:
            from configobj import ConfigObj
            oldcfg = ConfigObj(self.old_conffile)
            if oldcfg is None: oldcfg = { }
            conf = util.mergedict(conf,oldcfg)
        except:
            pass

        return(conf)

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
            os.makedirs(os.path.dirname(data_source_cache))
        except OSError as e:
            if e.errno != errno.EEXIST:
                return False
                
        try:
            f=open(data_source_cache, "wb")
            data = cPickle.dump(self.datasource,f)
            os.chmod(data_source_cache,0400)
            return True
        except:
            return False
        
    def get_cloud_type(self):
        pass

    def get_data_source(self):
        if self.datasource is not None: return True

        if self.restore_from_cache():
            log.debug("restored from cache type %s" % self.datasource)
            return True

        dslist=[ ]
        cfglist=self.cfg['cloud_type']
        if cfglist == "auto":
            dslist = self.auto_orders[self.source_type]
        elif cfglist:
            for ds in cfglist.split(','):
                dslist.append(strip(ds).tolower())
            
        for ds in dslist:
            if ds not in self.datasource_map:
                log.warn("data source %s not found in map" % ds)
                continue
            try:
                s = self.datasource_map[ds]()
                if s.get_data():
                    self.datasource = s
                    self.datasource_name = ds
                    log.debug("found data source %s" % ds)
                    return True
            except Exception as e:
                log.warn("get_data of %s raised %s" % (ds,e))
                util.logexc(log)
                pass
        log.debug("did not find data source from %s" % dslist)
        raise DataSourceNotFoundException("Could not find data source")

    def get_userdata(self):
        return(self.datasource.get_userdata())

    def update_cache(self):
        self.write_to_cache()
        self.store_userdata()

    def store_userdata(self):
        util.write_file(userdata_raw, self.datasource.get_userdata_raw(), 0600)
        util.write_file(userdata, self.datasource.get_userdata(), 0600)

    def initctl_emit(self):
        subprocess.Popen(['initctl', 'emit', 'cloud-config',
            '%s=%s' % (cfg_env_name,cloud_config)]).communicate()

    def sem_getpath(self,name,freq):
        freqtok = freq
        if freq == 'once-per-instance':
            freqtok = self.datasource.get_instance_id()

        return("%s/%s.%s" % (semdir,name,freqtok))
    
    def sem_has_run(self,name,freq):
        if freq == "always": return False
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
    
        if os.path.exists(semfile) and freq != "always":
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
        if self.sem_has_run(semname,freq):
            log.debug("%s already ran %s", semname, freq)
            return
        try:
            if not self.sem_acquire(semname,freq):
                raise Exception("Failed to acquire lock on %s" % semname)

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
        if ctype == "__end__": return
        if ctype == "__begin__" :
            self.handlercount = 0
            return

        # add the path to the plugins dir to the top of our list for import
        if self.handlercount == 0:
            sys.path.insert(0,pluginsdir)

        self.handlercount=self.handlercount+1

        # write content to pluginsdir
        modname  = 'part-handler-%03d' % self.handlercount
        modfname = modname + ".py"
        util.write_file("%s/%s" % (pluginsdir,modfname), payload, 0600)

        try:
            mod = __import__(modname)
            lister = getattr(mod, "list_types")
            handler = getattr(mod, "handle_part")
        except:
            import traceback
            traceback.print_exc(file=sys.stderr)
            return

        # - call it with '__begin__'
        handler(data, "__begin__", None, None)

        # - add it self.part_handlers
        for mtype in lister():
            self.part_handlers[mtype]=handler

    def handle_user_script(self,data,ctype,filename,payload):
        if ctype == "__end__": return
        if ctype == "__begin__":
            # maybe delete existing things here
            return

        filename=filename.replace(os.sep,'_')
        util.write_file("%s/%s" % (user_scripts_dir,filename), payload, 0700)

    def handle_upstart_job(self,data,ctype,filename,payload):
        if ctype == "__end__" or ctype == "__begin__": return
        if not filename.endswith(".conf"):
            filename=filename+".conf"

        util.write_file("%s/%s" % ("/etc/init",filename), payload, 0644)

    def handle_cloud_config(self,data,ctype,filename,payload):
        if ctype == "__begin__":
            self.cloud_config_str=""
            return
        if ctype == "__end__":
            util.write_file(cloud_config, self.cloud_config_str, 0600)

            ## this could merge the cloud config with the system config
            ## for now, not doing this as it seems somewhat circular
            ## as CloudConfig does that also, merging it with this cfg
            ##
            # ccfg = yaml.load(self.cloud_config_str)
            # if ccfg is None: ccfg = { }
            # self.cfg = util.mergedict(ccfg, self.cfg)

            return

        self.cloud_config_str+="\n#%s\n%s" % (filename,payload)

    def handle_cloud_boothook(self,data,ctype,filename,payload):
        if ctype == "__end__": return
        if ctype == "__begin__": return

        filename=filename.replace(os.sep,'_')
        prefix="#cloud-boothook"
        dos=False
        start = 0
        if payload.startswith(prefix):
            start = len(prefix)
            if payload[start] == '\r':
                start=start+1
                dos = True
        else:
            if payload.find('\r\n',0,100) >= 0:
                dos = True
    
        if dos:
            payload=payload[start:].replace('\r\n','\n')
        elif start != 0:
            payload=payload[start:]
    
        filepath = "%s/%s" % (boothooks_dir,filename)
        util.write_file(filepath, payload, 0700)
        try:
            env=os.environ.copy()
            env['INSTANCE_ID']= self.datasource.get_instance_id()
            ret = subprocess.check_call([filepath], env=env)
        except subprocess.CalledProcessError as e:
            log.error("boothooks script %s returned %i" %
                (filepath,e.returncode))
        except Exception as e:
            log.error("boothooks unknown exception %s when running %s" %
                (e,filepath))

    def get_public_ssh_keys(self):
        return(self.datasource.get_public_ssh_keys())

    def get_locale(self):
        return(self.datasource.get_locale())

    def get_mirror(self):
        return(self.datasource.get_local_mirror())

    def get_hostname(self):
        return(self.datasource.get_hostname())

    def device_name_to_device(self,name):
        return(self.datasource.device_name_to_device(name))


def purge_cache():
    try:
        os.unlink(data_source_cache)
    except OSError as e:
        if e.errno != errno.ENOENT: return(False)
    except:
        return(False)
    return(True)

class DataSourceNotFoundException(Exception):
    pass
