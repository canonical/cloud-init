# vi: ts=4 expandtab
#
#    Common code for the EC2 initialisation scripts in Ubuntu
#    Copyright (C) 2008-2009 Canonical Ltd
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Soren Hansen <soren@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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
log_cfgs: []
datasource_list: ["NoCloud", "ConfigDrive", "OVF", "MAAS", "Ec2", "CloudStack"]
def_log_file: /var/log/cloud-init.log
syslog_fix_perms: syslog:adm
"""
logger_name = "cloudinit"

pathmap = {
   "handlers": "/handlers",
   "scripts": "/scripts",
   "sem": "/sem",
   "boothooks": "/boothooks",
   "userdata_raw": "/user-data.txt",
   "userdata": "/user-data.txt.i",
   "obj_pkl": "/obj.pkl",
   "cloud_config": "/cloud-config.txt",
   "data": "/data",
   None: "",
}

per_instance = "once-per-instance"
per_always = "always"
per_once = "once"

parsed_cfgs = {}

import os

import cPickle
import sys
import os.path
import errno
import subprocess
import yaml
import logging
import logging.config
import StringIO
import glob
import traceback

import cloudinit.util as util


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


log = logging.getLogger(logger_name)
log.addHandler(NullHandler())


def logging_set_from_cfg_file(cfg_file=system_config):
    logging_set_from_cfg(util.get_base_cfg(cfg_file, cfg_builtin, parsed_cfgs))


def logging_set_from_cfg(cfg):
    log_cfgs = []
    logcfg = util.get_cfg_option_str(cfg, "log_cfg", False)
    if logcfg:
        # if there is a 'logcfg' entry in the config, respect
        # it, it is the old keyname
        log_cfgs = [logcfg]
    elif "log_cfgs" in cfg:
        for cfg in cfg['log_cfgs']:
            if isinstance(cfg, list):
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


import cloudinit.DataSource as DataSource
import cloudinit.UserDataHandler as UserDataHandler


class CloudInit:
    cfg = None
    part_handlers = {}
    old_conffile = '/etc/ec2-init/ec2-config.cfg'
    ds_deps = [DataSource.DEP_FILESYSTEM, DataSource.DEP_NETWORK]
    datasource = None
    cloud_config_str = ''
    datasource_name = ''

    builtin_handlers = []

    def __init__(self, ds_deps=None, sysconfig=system_config):
        self.builtin_handlers = [
            ['text/x-shellscript', self.handle_user_script, per_always],
            ['text/cloud-config', self.handle_cloud_config, per_always],
            ['text/upstart-job', self.handle_upstart_job, per_instance],
            ['text/cloud-boothook', self.handle_cloud_boothook, per_always],
        ]

        if ds_deps != None:
            self.ds_deps = ds_deps

        self.sysconfig = sysconfig

        self.cfg = self.read_cfg()

    def read_cfg(self):
        if self.cfg:
            return(self.cfg)

        try:
            conf = util.get_base_cfg(self.sysconfig, cfg_builtin, parsed_cfgs)
        except Exception:
            conf = get_builtin_cfg()

        # support reading the old ConfigObj format file and merging
        # it into the yaml dictionary
        try:
            from configobj import ConfigObj
            oldcfg = ConfigObj(self.old_conffile)
            if oldcfg is None:
                oldcfg = {}
            conf = util.mergedict(conf, oldcfg)
        except:
            pass

        return(conf)

    def restore_from_cache(self):
        try:
            # we try to restore from a current link and static path
            # by using the instance link, if purge_cache was called
            # the file wont exist
            cache = get_ipath_cur('obj_pkl')
            f = open(cache, "rb")
            data = cPickle.load(f)
            f.close()
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
            f = open(cache, "wb")
            cPickle.dump(self.datasource, f)
            f.close()
            os.chmod(cache, 0400)
        except:
            raise

    def get_data_source(self):
        if self.datasource is not None:
            return True

        if self.restore_from_cache():
            log.debug("restored from cache type %s" % self.datasource)
            return True

        cfglist = self.cfg['datasource_list']
        dslist = list_sources(cfglist, self.ds_deps)
        dsnames = [f.__name__ for f in dslist]

        log.debug("searching for data source in %s" % dsnames)
        for cls in dslist:
            ds = cls.__name__
            try:
                s = cls(sys_cfg=self.cfg)
                if s.get_data():
                    self.datasource = s
                    self.datasource_name = ds
                    log.debug("found data source %s" % ds)
                    return True
            except Exception as e:
                log.warn("get_data of %s raised %s" % (ds, e))
                util.logexc(log)
        msg = "Did not find data source. searched classes: %s" % dsnames
        log.debug(msg)
        raise DataSourceNotFoundException(msg)

    def set_cur_instance(self):
        try:
            os.unlink(cur_instance_link)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise

        iid = self.get_instance_id()
        os.symlink("./instances/%s" % iid, cur_instance_link)
        idir = self.get_ipath()
        dlist = []
        for d in ["handlers", "scripts", "sem"]:
            dlist.append("%s/%s" % (idir, d))

        util.ensure_dirs(dlist)

        ds = "%s: %s\n" % (self.datasource.__class__, str(self.datasource))
        dp = self.get_cpath('data')
        util.write_file("%s/%s" % (idir, 'datasource'), ds)
        util.write_file("%s/%s" % (dp, 'previous-datasource'), ds)
        util.write_file("%s/%s" % (dp, 'previous-instance-id'), "%s\n" % iid)

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

    def sem_getpath(self, name, freq):
        if freq == 'once-per-instance':
            return("%s/%s" % (self.get_ipath("sem"), name))
        return("%s/%s.%s" % (get_cpath("sem"), name, freq))

    def sem_has_run(self, name, freq):
        if freq == per_always:
            return False
        semfile = self.sem_getpath(name, freq)
        if os.path.exists(semfile):
            return True
        return False

    def sem_acquire(self, name, freq):
        from time import time
        semfile = self.sem_getpath(name, freq)

        try:
            os.makedirs(os.path.dirname(semfile))
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise e

        if os.path.exists(semfile) and freq != per_always:
            return False

        # race condition
        try:
            f = open(semfile, "w")
            f.write("%s\n" % str(time()))
            f.close()
        except:
            return(False)
        return(True)

    def sem_clear(self, name, freq):
        semfile = self.sem_getpath(name, freq)
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
    def sem_and_run(self, semname, freq, func, args=None, clear_on_fail=False):
        if args is None:
            args = []
        if self.sem_has_run(semname, freq):
            log.debug("%s already ran %s", semname, freq)
            return False
        try:
            if not self.sem_acquire(semname, freq):
                raise Exception("Failed to acquire lock on %s" % semname)

            func(*args)
        except:
            if clear_on_fail:
                self.sem_clear(semname, freq)
            raise

        return True

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/name)<name>)
    def get_ipath(self, name=None):
        return("%s/instances/%s%s"
               % (varlibdir, self.get_instance_id(), pathmap[name]))

    def consume_userdata(self, frequency=per_instance):
        self.get_userdata()
        data = self

        cdir = get_cpath("handlers")
        idir = self.get_ipath("handlers")

        # add the path to the plugins dir to the top of our list for import
        # instance dir should be read before cloud-dir
        sys.path.insert(0, cdir)
        sys.path.insert(0, idir)

        part_handlers = {}
        # add handlers in cdir
        for fname in glob.glob("%s/*.py" % cdir):
            if not os.path.isfile(fname):
                continue
            modname = os.path.basename(fname)[0:-3]
            try:
                mod = __import__(modname)
                handler_register(mod, part_handlers, data, frequency)
                log.debug("added handler for [%s] from %s" % (mod.list_types(),
                                                              fname))
            except:
                log.warn("failed to initialize handler in %s" % fname)
                util.logexc(log)

        # add the internal handers if their type hasn't been already claimed
        for (btype, bhand, bfreq) in self.builtin_handlers:
            if btype in part_handlers:
                continue
            handler_register(InternalPartHandler(bhand, [btype], bfreq),
                part_handlers, data, frequency)

        # walk the data
        pdata = {'handlers': part_handlers, 'handlerdir': idir,
                 'data': data, 'frequency': frequency}
        UserDataHandler.walk_userdata(self.get_userdata(),
            partwalker_callback, data=pdata)

        # give callbacks opportunity to finalize
        called = []
        for (_mtype, mod) in part_handlers.iteritems():
            if mod in called:
                continue
            handler_call_end(mod, data, frequency)

    def handle_user_script(self, _data, ctype, filename, payload, _frequency):
        if ctype == "__end__":
            return
        if ctype == "__begin__":
            # maybe delete existing things here
            return

        filename = filename.replace(os.sep, '_')
        scriptsdir = get_ipath_cur('scripts')
        util.write_file("%s/%s" %
            (scriptsdir, filename), util.dos2unix(payload), 0700)

    def handle_upstart_job(self, _data, ctype, filename, payload, frequency):
        # upstart jobs are only written on the first boot
        if frequency != per_instance:
            return

        if ctype == "__end__" or ctype == "__begin__":
            return
        if not filename.endswith(".conf"):
            filename = filename + ".conf"

        util.write_file("%s/%s" % ("/etc/init", filename),
            util.dos2unix(payload), 0644)

    def handle_cloud_config(self, _data, ctype, filename, payload, _frequency):
        if ctype == "__begin__":
            self.cloud_config_str = ""
            return
        if ctype == "__end__":
            cloud_config = self.get_ipath("cloud_config")
            util.write_file(cloud_config, self.cloud_config_str, 0600)

            ## this could merge the cloud config with the system config
            ## for now, not doing this as it seems somewhat circular
            ## as CloudConfig does that also, merging it with this cfg
            ##
            # ccfg = yaml.load(self.cloud_config_str)
            # if ccfg is None: ccfg = {}
            # self.cfg = util.mergedict(ccfg, self.cfg)

            return

        self.cloud_config_str += "\n#%s\n%s" % (filename, payload)

    def handle_cloud_boothook(self, _data, ctype, filename, payload,
                              _frequency):
        if ctype == "__end__":
            return
        if ctype == "__begin__":
            return

        filename = filename.replace(os.sep, '_')
        payload = util.dos2unix(payload)
        prefix = "#cloud-boothook"
        start = 0
        if payload.startswith(prefix):
            start = len(prefix) + 1

        boothooks_dir = self.get_ipath("boothooks")
        filepath = "%s/%s" % (boothooks_dir, filename)
        util.write_file(filepath, payload[start:], 0700)
        try:
            env = os.environ.copy()
            env['INSTANCE_ID'] = self.datasource.get_instance_id()
            subprocess.check_call([filepath], env=env)
        except subprocess.CalledProcessError as e:
            log.error("boothooks script %s returned %i" %
                (filepath, e.returncode))
        except Exception as e:
            log.error("boothooks unknown exception %s when running %s" %
                (e, filepath))

    def get_public_ssh_keys(self):
        return(self.datasource.get_public_ssh_keys())

    def get_locale(self):
        return(self.datasource.get_locale())

    def get_mirror(self):
        return(self.datasource.get_local_mirror())

    def get_hostname(self, fqdn=False):
        return(self.datasource.get_hostname(fqdn=fqdn))

    def device_name_to_device(self, name):
        return(self.datasource.device_name_to_device(name))

    # I really don't know if this should be here or not, but
    # I needed it in cc_update_hostname, where that code had a valid 'cloud'
    # reference, but did not have a cloudinit handle
    # (ie, no cloudinit.get_cpath())
    def get_cpath(self, name=None):
        return(get_cpath(name))


def initfs():
    subds = ['scripts/per-instance', 'scripts/per-once', 'scripts/per-boot',
             'seed', 'instances', 'handlers', 'sem', 'data']
    dlist = []
    for subd in subds:
        dlist.append("%s/%s" % (varlibdir, subd))
    util.ensure_dirs(dlist)

    cfg = util.get_base_cfg(system_config, cfg_builtin, parsed_cfgs)
    log_file = util.get_cfg_option_str(cfg, 'def_log_file', None)
    perms = util.get_cfg_option_str(cfg, 'syslog_fix_perms', None)
    if log_file:
        fp = open(log_file, "ab")
        fp.close()
    if log_file and perms:
        (u, g) = perms.split(':', 1)
        if u == "-1" or u == "None":
            u = None
        if g == "-1" or g == "None":
            g = None
        util.chownbyname(log_file, u, g)


def purge_cache(rmcur=True):
    rmlist = [boot_finished]
    if rmcur:
        rmlist.append(cur_instance_link)
    for f in rmlist:
        try:
            os.unlink(f)
        except OSError as e:
            if e.errno == errno.ENOENT:
                continue
            return(False)
        except:
            return(False)
    return(True)


# get_ipath_cur: get the current instance path for an item
def get_ipath_cur(name=None):
    return("%s/%s%s" % (varlibdir, "instance", pathmap[name]))


# get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
# for a name in dirmap
def get_cpath(name=None):
    return("%s%s" % (varlibdir, pathmap[name]))


def get_base_cfg(cfg_path=None):
    if cfg_path is None:
        cfg_path = system_config
    return(util.get_base_cfg(cfg_path, cfg_builtin, parsed_cfgs))


def get_builtin_cfg():
    return(yaml.load(cfg_builtin))


class DataSourceNotFoundException(Exception):
    pass


def list_sources(cfg_list, depends):
    return(DataSource.list_sources(cfg_list, depends, ["cloudinit", ""]))


def handler_register(mod, part_handlers, data, frequency=per_instance):
    if not hasattr(mod, "handler_version"):
        setattr(mod, "handler_version", 1)

    for mtype in mod.list_types():
        part_handlers[mtype] = mod

    handler_call_begin(mod, data, frequency)
    return(mod)


def handler_call_begin(mod, data, frequency):
    handler_handle_part(mod, data, "__begin__", None, None, frequency)


def handler_call_end(mod, data, frequency):
    handler_handle_part(mod, data, "__end__", None, None, frequency)


def handler_handle_part(mod, data, ctype, filename, payload, frequency):
    # only add the handler if the module should run
    modfreq = getattr(mod, "frequency", per_instance)
    if not (modfreq == per_always or
            (frequency == per_instance and modfreq == per_instance)):
        return
    try:
        if mod.handler_version == 1:
            mod.handle_part(data, ctype, filename, payload)
        else:
            mod.handle_part(data, ctype, filename, payload, frequency)
    except:
        util.logexc(log)
        traceback.print_exc(file=sys.stderr)


def partwalker_handle_handler(pdata, _ctype, _filename, payload):
    curcount = pdata['handlercount']
    modname = 'part-handler-%03d' % curcount
    frequency = pdata['frequency']

    modfname = modname + ".py"
    util.write_file("%s/%s" % (pdata['handlerdir'], modfname), payload, 0600)

    try:
        mod = __import__(modname)
        handler_register(mod, pdata['handlers'], pdata['data'], frequency)
        pdata['handlercount'] = curcount + 1
    except:
        util.logexc(log)
        traceback.print_exc(file=sys.stderr)


def partwalker_callback(pdata, ctype, filename, payload):
    # data here is the part_handlers array and then the data to pass through
    if ctype == "text/part-handler":
        if 'handlercount' not in pdata:
            pdata['handlercount'] = 0
        partwalker_handle_handler(pdata, ctype, filename, payload)
        return
    if ctype not in pdata['handlers']:
        if ctype == "text/x-not-multipart":
            # Extract the first line or 24 bytes for displaying in the log
            start = payload.split("\n", 1)[0][:24]
            if start < payload:
                details = "starting '%s...'" % start.encode("string-escape")
            else:
                details = repr(payload)
            log.warning("Unhandled non-multipart userdata %s", details)
        return
    handler_handle_part(pdata['handlers'][ctype], pdata['data'],
        ctype, filename, payload, pdata['frequency'])


class InternalPartHandler:
    freq = per_instance
    mtypes = []
    handler_version = 1
    handler = None

    def __init__(self, handler, mtypes, frequency, version=2):
        self.handler = handler
        self.mtypes = mtypes
        self.frequency = frequency
        self.handler_version = version

    def __repr__(self):
        return("InternalPartHandler: [%s]" % self.mtypes)

    def list_types(self):
        return(self.mtypes)

    def handle_part(self, data, ctype, filename, payload, frequency):
        return(self.handler(data, ctype, filename, payload, frequency))


def get_cmdline_url(names=('cloud-config-url', 'url'),
                    starts="#cloud-config", cmdline=None):

    if cmdline == None:
        cmdline = util.get_cmdline()

    data = util.keyval_str_to_dict(cmdline)
    url = None
    key = None
    for key in names:
        if key in data:
            url = data[key]
            break
    if url == None:
        return (None, None, None)

    contents = util.readurl(url)

    if contents.startswith(starts):
        return (key, url, contents)

    return (key, url, None)
