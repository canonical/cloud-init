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

from time import time

import cPickle as pickle

import contextlib
import copy
import os
import sys
import weakref

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS)
from cloudinit.settings import (OLD_CLOUD_CONFIG, CLOUD_CONFIG)

from cloudinit import (get_builtin_cfg, get_base_cfg)
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util
from cloudinit import handlers

from cloudinit import user_data as ud
from cloudinit.user_data import boot_hook as bh_part
from cloudinit.user_data import cloud_config as cc_part
from cloudinit.user_data import processor as ud_proc
from cloudinit.user_data import shell_script as ss_part
from cloudinit.user_data import upstart_job as up_part

LOG = logging.getLogger(__name__)


class CloudSemaphores(object):
    def __init__(self, sem_path):
        self.sem_path = sem_path

    # acquire lock on 'name' for given 'freq' and run function 'func'
    # if 'clear_on_fail' is True and 'func' throws an exception
    # then remove the lock (so it would run again)
    def run_functor(self, name, freq, functor, args=None, clear_on_fail=False):
        if not args:
            args = []
        if self.has_run(name, freq):
            LOG.debug("%s already ran %s", name, freq)
            return False
        with self.lock(name, freq, clear_on_fail) as lock:
            if not lock:
                raise RuntimeError("Failed to acquire lock on %s" % name)
            else:
                LOG.debug("Running %s with args %s using lock %s", func, args, lock)
                func(*args)
        return True

    @contextlib.contextmanager
    def lock(self, name, freq, clear_on_fail=False):
        try:
            yield self._acquire(name, freq)
        except:
            if clear_on_fail:
                self.clear(name, freq)
            raise

    def clear(self, name, freq):
        sem_file = self._getpath(name, freq)
        try:
            util.del_file(sem_file)
        except IOError:
            return False
        return True

    def _acquire(self, name, freq):
        if self.has_run(name, freq):
            return None
        # This is a race condition since nothing atomic is happening
        # here, but this should be ok due to the nature of when
        # and where cloud-init runs... (file writing is not a lock..)
        sem_file = self._getpath(name, freq)
        contents = "%s: %s\n" % (os.getpid(), time())
        try:
            util.write_file(sem_file, contents)
        except (IOError, OSError):
            return None
        return sem_file

    def has_run(self, name, freq):
        if freq == PER_ALWAYS:
            return False
        sem_file = self._get_path(name, freq)
        if os.path.exists(sem_file):
            return True
        return False

    def _get_path(self, name, freq):
        sem_path = self.sem_path
        if freq == PER_INSTANCE:
            return os.path.join(sem_path, name)
        return os.path.join(sem_path, "%s.%s" % (name, freq))


class CloudPaths(object):
    def __init__(self, sys_info):
        self.cloud_dir = sys_info['cloud_dir']
        self.instance_link = os.path.join(self.cloud_dir, 'instance')
        self.boot_finished = os.path.join(self.instance_link, "boot-finished")
        self.upstart_conf_d = sys_info.get('upstart_dir')
        self.template_dir = sys_info['templates_dir']
        self.seed_dir = os.path.join(self.cloud_dir, 'seed')
        self.datasource = None
        self.lookups = {
           "handlers": "handlers",
           "scripts": "scripts",
           "sem": "sem",
           "boothooks": "boothooks",
           "userdata_raw": "user-data.txt",
           "userdata": "user-data.txt.i",
           "obj_pkl": "obj.pkl",
           "cloud_config": "cloud-config.txt",
           "data": "data",
        }

    # get_ipath_cur: get the current instance path for an item
    def get_ipath_cur(self, name=None):
        ipath = os.path.join(self.cloud_dir, 'instance')
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
    # for a name in dirmap
    def get_cpath(self, name=None):
        cpath = self.var_dir
        add_on = self.lookups.get(name)
        if add_on:
            cpath = os.path.join(cpath, add_on)
        return cpath

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    def get_ipath(self, name=None):
        if not self.datasource:
            raise RuntimeError("Unable to get instance path, datasource not available/set.")
        iid = self.datasource.get_instance_id()
        ipath = os.path.join(self.cloud_dir, 'instances', iid)
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath


class CloudSimple(object):
    def __init__(self, ci):
        self.datasource = init.datasource
        self.paths = init.paths
        self.cfg = copy.deepcopy(ci.cfg)

    def get_userdata(self):
        return self.datasource.get_userdata()

    def get_public_ssh_keys(self):
        return self.datasource.get_public_ssh_keys()

    def get_locale(self):
        return self.datasource.get_locale()

    def get_mirror(self):
        return self.datasource.get_local_mirror()

    def get_hostname(self, fqdn=False):
        return self.datasource.get_hostname(fqdn=fqdn)

    def device_name_to_device(self, name):
        return self.datasource.device_name_to_device(name)

    def get_ipath_cur(self, name=None):
        return self.paths.get_ipath_cur(name)

    def get_cpath(self, name=None):
        return self.paths.get_cpath(name)

    def get_ipath(self, name=None):
        return self.paths.get_ipath(name)


class CloudInit(object):
    def __init__(self, ds_deps=None):
        self.datasource = None
        if ds_deps:
            self.ds_deps = ds_deps
        else:
            self.ds_deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
        self.cfg = self._read_cfg()
        self.paths = CloudPaths(self.cfg['system_info'])

    def _read_cfg_old(self):
        # support reading the old ConfigObj format file and merging
        # it into the yaml dictionary
        try:
            from configobj import ConfigObj
        except ImportError:
            ConfigObj = None
        if not ConfigObj:
            return {}
        old_cfg = ConfigObj(OLD_CLOUD_CONFIG)
        return dict(old_cfg)

    def _initial_subdirs(self):
        c_dir = self.paths.cloud_dir
        initial_dirs = [
            os.path.join(c_dir, 'scripts'),
            os.path.join(c_dir, 'scripts', 'per-instance'),
            os.path.join(c_dir, 'scripts', 'per-once'),
            os.path.join(c_dir, 'scripts', 'per-boot'),
            os.path.join(c_dir, 'seed'),
            os.path.join(c_dir, 'instances'),
            os.path.join(c_dir, 'handlers'),
            os.path.join(c_dir, 'sem'),
            os.path.join(c_dir, 'data'),
        ]
        return initial_dirs

    def purge_cache(self, rmcur=True):
        rmlist = []
        rmlist.append(self.paths.boot_finished)
        if rmcur:
            rmlist.append(self.paths.instance_link)
        for f in rmlist:
            util.unlink(f)
        return len(rmlist)

    def init_fs(self):
        util.ensure_dirs(self._initial_subdirs())
        log_file = util.get_cfg_option_str(self.cfg, 'def_log_file', None)
        perms = util.get_cfg_option_str(self.cfg, 'syslog_fix_perms', None)
        if log_file:
            util.ensure_file(log_file)
            if perms:
                (u, g) = perms.split(':', 1)
                if u == "-1" or u == "None":
                    u = None
                if g == "-1" or g == "None":
                    g = None
                util.chownbyname(log_file, u, g)

    def _read_cfg(self):
        starting_config = get_builtin_cfg()
        try:
            conf = get_base_cfg(CLOUD_CONFIG, starting_config)
        except Exception:
            conf = starting_config
        old_conf = self._read_cfg_old()
        conf = util.mergedict(conf, old_conf)
        return conf
    
    def _restore_from_cache(self):
        pickled_fn = self.paths.get_ipath_cur('obj_pkl')
        try:
            # we try to restore from a current link and static path
            # by using the instance link, if purge_cache was called
            # the file wont exist
            return pickle.loads(util.load_file(pickled_fn))
        except Exception as e:
            LOG.debug("Failed loading pickled datasource from %s due to %s", pickled_fn, e)
            return False

    def write_to_cache(self):
        pickled_fn = self.paths.get_ipath_cur("obj_pkl")
        try:
            contents = pickle.dumps(self.datasource)
            util.write_file(pickled_fn, contents, mode=0400)
        except Exception as e:
            LOG.debug("Failed pickling datasource to %s due to: %s", pickled_fn, e)
            return False

    def _get_processor(self):
        return ud_proc.UserDataProcessor(self.paths)

    def _get_datasources(self):
        # Any config provided???
        pkg_list = self.cfg.get('datasource_pkg_list') or []
        # Add the defaults at the end
        for n in [util.obj_name(sources), '']:
            if n not in pkg_list:
                pkg_list.append(n)
        cfg_list = self.cfg.get('datasource_list') or []
        return (cfg_list, pkg_list)

    def get_data_source(self):
        if self.datasource:
            return True
        ds = self._restore_from_cache()
        if ds:
            LOG.debug("Restored from cache datasource: %s" % ds)
        else:
            (cfg_list, pkg_list) = self._get_datasources()
            ud_proc = self._get_processor()
            (ds, dsname) = sources.find_source(self.cfg,
                                               self.ds_deps,
                                               cfg_list=cfg_list,
                                               pkg_list=pkg_list,
                                               ud_proc=ud_proc)
            LOG.debug("Loaded datasource %s - %s", dsname, ds)
        self.datasource = ds
        # This allows the paths obj to have an ipath function that works
        self.paths.datasource = ds
        return True

    def set_cur_instance(self):
        # Ensure we are hooked into the right symlink for the current instance
        idir = self.paths.get_ipath()
        util.del_file(self.paths.instance_link)
        util.sym_link(idir, self.paths.instance_link)

        dlist = []
        for d in ["handlers", "scripts", "sem"]:
            dlist.append(os.path.join(idir, d))
        util.ensure_dirs(dlist)

        # Write out information on what is being used for the current instance
        # and what may have been used for a previous instance...
        dp = self.paths.get_cpath('data')
        ds = "%s: %s\n" % (self.datasource.__class__, self.datasource)
        previous_ds = ''
        ds_fn = os.path.join(idir, 'datasource')
        try:
            previous_ds = util.load_file(ds_fn).strip()
        except IOError as e:
            pass
        if not previous_ds:
            # TODO: ?? is this right
            previous_ds = ds
        util.write_file(ds_fn, ds)
        util.write_file(os.path.join(dp, 'previous-datasource'), previous_ds)
        iid = self.datasource.get_instance_id()
        previous_iid = ''
        p_iid_fn = os.path.join(dp, 'previous-instance-id')
        try:
            previous_iid = util.load_file(p_iid_fn).strip()
        except IOError as e:
            pass
        if not previous_iid:
            # TODO: ?? is this right
            previous_iid = iid
        util.write_file(p_iid_fn, "%s\n" % previous_iid)

    def update_cache(self):
        self.write_to_cache()
        self.store_userdata()

    def store_userdata(self):
        raw_ud = "%s" % (self.datasource.get_userdata_raw())
        util.write_file(self.paths.get_ipath('userdata_raw'), raw_ud, 0600)
        ud = "%s" % (self.datasource.get_userdata())
        util.write_file(self.paths.get_ipath('userdata'), ud, 0600)

    def consume_userdata(self, frequency=PER_INSTANCE):
        cdir = self.paths.get_cpath("handlers")
        idir = self.paths.get_ipath("handlers")
    
        # Add the path to the plugins dir to the top of our list for import
        # instance dir should be read before cloud-dir
        sys.path.insert(0, cdir)
        sys.path.insert(0, idir)

        # Data will be a little proxy that modules can use
        data = CloudSimple(self)

        # This keeps track of all the active handlers
        handlers = CloudHandlers(self)

        # Add handlers in cdir
        potential_handlers = utils.find_modules(cdir)
        for (fname, modname) in potential_handlers.iteritems():
            try:
                mod = parts.fixup_module(importer.import_module(modname))
                types = handlers.register(mod)
                LOG.debug("Added handler for [%s] from %s", types, fname)
            except:
                LOG.exception("Failed to register handler from %s", fname)

        def_handlers = handlers.register_defaults()
        if def_handlers:
            LOG.debug("Registered default handlers for [%s]", def_handlers)

        # Init the handlers first
        # Ensure userdata fetched before activation
        called = []
        for (_mtype, mod) in handlers.iteritems():
            if mod in called:
                continue
            parts.call_begin(mod, data, frequency)
            called.append(mod)

        # Walk the user data
        part_data = {
            'handlers': handlers,
            'handlerdir': idir,
            'data': data, 
            'frequency': frequency,
            'handlercount': 0,
        }
        ud.walk(data.get_userdata(), parts.walker_callback, data=part_data)

        # Give callbacks opportunity to finalize
        called = []
        for (_mtype, mod) in handlers.iteritems():
            if mod in called:
                continue
            parts.call_end(mod, data, frequency)
            called.append(mod)


class CloudHandlers(object):

    def __init__(self, paths):
        self.paths = paths
        self.registered = {}

    def __contains__(self, item):
        return self.is_registered(item)

    def __getitem__(self, key):
        return self._get_handler(key)

    def is_registered(self, content_type):
        return content_type in self.registered

    def register(self, mod):
        types = set()
        for t in mod.list_types():
            self.registered[t] = handler
            types.add(t)
        return types

    def _get_handler(self, content_type):
        return self.registered[content_type]

    def items(self):
        return self.registered.items()

    def iteritems(self):
        return self.registered.iteritems()

    def _get_default_handlers(self):
        def_handlers = []
        if self.paths.get_ipath("cloud_config"):
            def_handlers.append(cc_part.CloudConfigPartHandler(self.paths.get_ipath("cloud_config")))
        if self.paths.get_ipath_cur('scripts'):
            def_handlers.append(ss_part.ShellScriptPartHandler(self.paths.get_ipath_cur('scripts')))
        if self.paths.get_ipath("boothooks"):
            def_handlers.append(bh_part.BootHookPartHandler(self.paths.get_ipath("boothooks")))
        if self.paths.upstart_conf_d:
            def_handlers.append(up_part.UpstartJobPartHandler(self.paths.upstart_conf_d))
        return def_handlers

    def register_defaults(self):
        registered = set()
        for h in self._get_default_handlers():
            for t in h.list_types():
                if not self.is_registered(t)
                    self.register_handler(t, h)
                    registered.add(t)
        return registered


class CloudConfig(object):
    def __init__(self, cfgfile, cloud):
        self.cloud = cloud
        self.cfg = self._get_config(cfgfile)
        self.paths = cloud.paths
        self.sems = CloudSemaphores(self.paths.get_ipath("sem"))

    def _get_config(self, cfgfile):
        cfg = None
        try:
            cfg = util.read_conf(cfgfile)
        except:
            LOG.exception(("Failed loading of cloud config '%s'. "
                          "Continuing with empty config."), cfgfile)
        if not cfg:
            cfg = {}

        ds_cfg = None
        try:
            ds_cfg = self.cloud.datasource.get_config_obj()
        except:
            LOG.exception("Failed loading of datasource config.")
        if not ds_cfg:
            ds_cfg = {}

        cfg = util.mergedict(cfg, ds_cfg)
        cloud_cfg = self.cloud.cfg or {}
        return util.mergedict(cfg, cloud_cfg)

    def extract(self, name):
        modname = handlers.form_module_name(name)
        if not modname:
            return None
        return handlers.fixup_module(importer.import_module(modname))

    def handle(self, name, mod, args, freq=None):
        def_freq = mod.frequency 
        if not freq:
            freq = def_freq
        c_name = "config-%s" % (name)
        real_args = [name, copy.deepcopy(self.cfg), CloudSimple(self.cloud), LOG, copy.deepcopy(args)]
        return self.sems.run_functor(c_name, freq, mod.handle, real_args)
