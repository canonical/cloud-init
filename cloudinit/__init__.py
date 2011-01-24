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

varlibdir = '/var/lib/cloud'
cur_instance_link = varlibdir + "/instance"
boot_finished = cur_instance_link + "/boot-finished"
system_config = '/etc/cloud/cloud.cfg'
seeddir = varlibdir + "/seed"
cfg_env_name = "CLOUD_CFG"

cfg_builtin = """
log_cfgs: [ ]
cloud_type: auto
def_log_file: /var/log/cloud-init.log
syslog_fix_perms: syslog:adm
"""
logger_name = "cloudinit"

pathmap = {
   "handlers" : "/handlers",
   "scripts" : "/scripts",
   "sem" : "/sem",
   "boothooks" : "/boothooks",
   "userdata_raw" : "/user-data.txt",
   "userdata" : "/user-data-raw.txt.i",
   "obj_pkl" : "/obj.pkl",
   "cloud_config" : "/cloud-config.txt",
   "datadir" : "/data",
   None : "",
}

parsed_cfgs = { }

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
import glob

class NullHandler(logging.Handler):
    def emit(self,record): pass

log = logging.getLogger(logger_name)
log.addHandler(NullHandler())

def logging_set_from_cfg_file(cfg_file=system_config):
    logging_set_from_cfg(util.get_base_cfg(cfg_file,cfg_builtin,parsed_cfgs))

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
        return

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

        conf = util.get_base_cfg(self.sysconfig,cfg_builtin, parsed_cfgs)

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
            # we try to restore from a current link and static path
            # by using the instance link, if purge_cache was called
            # the file wont exist
            cache = get_ipath_cur('obj_pkl')
            f=open(cache, "rb")
            data = cPickle.load(f)
            self.datasource = data
            return True
        except:
            return False

    def write_to_cache(self):
        cache = self.get_ipath("obj_pkl")
        try:
            os.makedirs(os.path.dirname(cache))
        except OSError as e:
            if e.errno != errno.EEXIST:
                return False
                
        try:
            f=open(cache, "wb")
            data = cPickle.dump(self.datasource,f)
            os.chmod(cache,0400)
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
            
        log.debug("searching for data source in [%s]" % str(dslist))
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

    def set_cur_instance(self):
        try:
            os.unlink(cur_instance_link)
        except OSError, e:
            if e.errno != errno.ENOENT: raise

        os.symlink("./instances/%s" % self.get_instance_id(), cur_instance_link)
        idir = self.get_ipath()
        dlist = []
        for d in [ "handlers", "scripts", "sem" ]:
            dlist.append("%s/%s" % (idir, d))
            
        util.ensure_dirs(dlist)

    def get_userdata(self):
        return(self.datasource.get_userdata())

    def get_userdata_raw(self):
        return(self.datasource.get_userdata_raw())

    def get_instance_id(self):
        return(self.datasource.get_instance_id())

    def update_cache(self):
        self.write_to_cache()
        self.store_userdata()

    def store_userdata(self):
        util.write_file(self.get_ipath('userdata_raw'),
            self.datasource.get_userdata_raw(), 0600)
        util.write_file(self.get_ipath('userdata'),
            self.datasource.get_userdata(), 0600)

    def initctl_emit(self):
        cc_path = get_ipath_cur('cloud_config')
        subprocess.Popen(['initctl', 'emit', 'cloud-config',
            '%s=%s' % (cfg_env_name,cc_path)]).communicate()

    def sem_getpath(self,name,freq):
        if freq == 'once-per-instance':
            return("%s/%s" % (self.get_ipath("sem"),name))
        return("%s/%s.%s" % (get_cpath("sem"), name, freq))
    
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

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/name)<name>)
    def get_ipath(self, name=None):
        return("%s/instances/%s%s" 
               % (varlibdir,self.get_instance_id(), pathmap[name]))

    def consume_userdata(self):
        self.get_userdata()
        data = self

        cdir = get_cpath("handlers")
        idir = self.get_ipath("handlers")

        # add the path to the plugins dir to the top of our list for import
        # instance dir should be read before cloud-dir
        sys.path.insert(0,cdir)
        sys.path.insert(0,idir)

        # add handlers in cdir
        for fname in glob.glob("%s/*.py" % cdir):
            if not os.path.isfile(fname): continue
            modname = os.path.basename(fname)[0:-3]
            try:
                mod = __import__(modname)
                lister = getattr(mod, "list_types")
                handler = getattr(mod, "handle_part")
                mtypes = lister()
                for mtype in mtypes:
                    self.part_handlers[mtype]=handler
                log.debug("added handler for [%s] from %s" % (mtypes,fname))
            except:
                log.warn("failed to initialize handler in %s" % fname)
                util.logexc(log)
       
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

        self.handlercount=self.handlercount+1

        # write content to instance's handlerdir
        handlerdir = self.get_ipath("handler")
        modname  = 'part-handler-%03d' % self.handlercount
        modfname = modname + ".py"
        util.write_file("%s/%s" % (handlerdir,modfname), payload, 0600)

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
        scriptsdir = get_ipath_cur('scripts')
        util.write_file("%s/%s/%s" % 
            (scriptsdir,self.get_instance_id(),filename), payload, 0700)

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
            cloud_config = self.get_ipath("cloud_config")
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
    
        boothooks_dir = self.get_ipath("boothooks")
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

    # I really don't know if this should be here or not, but
    # I needed it in cc_update_hostname, where that code had a valid 'cloud'
    # reference, but did not have a cloudinit handle
    # (ie, no cloudinit.get_cpath())
    def get_cpath(self,name=None):
        return(get_cpath(name))


def initfs():
    subds = [ 'scripts/per-instance', 'scripts/per-once', 'scripts/per-boot',
              'seed', 'instances', 'handlers', 'sem', 'data' ]
    dlist = [ ]
    for subd in subds:
        dlist.append("%s/%s" % (varlibdir, subd))
    util.ensure_dirs(dlist)

    cfg = util.get_base_cfg(system_config,cfg_builtin,parsed_cfgs)
    log_file = None
    if 'def_log_file' in cfg:
        log_file = cfg['def_log_file']
        fp = open(log_file,"ab")
        fp.close()
    if log_file and 'syslog' in cfg:
        perms = cfg['syslog']
        (u,g) = perms.split(':',1)
        if u == "-1" or u == "None": u = None
        if g == "-1" or g == "None": g = None
        util.chownbyname(log_file, u, g)

def purge_cache():
    rmlist = ( boot_finished , cur_instance_link )
    for f in rmlist:
        try:
            os.unlink(f)
        except OSError as e:
            if e.errno == errno.ENOENT: continue
            return(False)
        except:
            return(False)
    return(True)

# get_ipath_cur: get the current instance path for an item
def get_ipath_cur(name=None):
    return("%s/instance/%s" % (varlibdir, pathmap[name]))

# get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
# for a name in dirmap
def get_cpath(name=None):
    return("%s%s" % (varlibdir, pathmap[name]))

class DataSourceNotFoundException(Exception):
    pass
