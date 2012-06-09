from time import time

import cPickle as pickle
import contextlib
import os
import sys
import weakref


from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS,
                                OLD_CLOUD_CONFIG, CLOUD_CONFIG,
                                CFG_BUILTIN, CUR_INSTANCE_LINK)
from cloudinit import (get_builtin_cfg, get_base_cfg)
from cloudinit import log as logging
from cloudinit import parts
from cloudinit import sources
from cloudinit import util
from cloudinit import user_data

LOG = logging.getLogger(__name__)


class CloudSemaphores(object):
    def __init__(self, paths):
        self.paths = paths

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
        contents = "%s\n" % str(time())
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
        sem_path = self.init.get_ipath("sem")
        if freq == PER_INSTANCE:
            return os.path.join(sem_path, name)
        return os.path.join(sem_path, "%s.%s" % (name, freq))


class CloudPaths(object):
    def __init__(self, init):
        self.config = CLOUD_CONFIG
        self.old_config = OLD_CLOUD_CONFIG
        self.var_dir = VAR_LIB_DIR
        self.instance_link = CUR_INSTANCE_LINK
        self.init = weakref.proxy(init)
        self.upstart_conf_d = "/etc/init"

    def _get_path_key(self, name):
        return PATH_MAP.get(name)

    # get_ipath_cur: get the current instance path for an item
    def get_ipath_cur(self, name=None):
        add_on = self._get_path_key(name)
        ipath = os.path.join(self.var_dir, 'instance')
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
    # for a name in dirmap
    def get_cpath(self, name=None):
        cpath = self.var_dir
        add_on = self._get_path_key(name)
        if add_on:
            cpath = os.path.join(cpath, add_on)
        return cpath

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    def get_ipath(self, name=None):
        iid = self.init.datasource.get_instance_id()
        ipath = os.path.join(self.var_dir, 'instances', iid)
        add_on = self._get_path_key(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath


class CloudPartData(object):
    def __init__(self, datasource, paths):
        self.datasource = datasource
        self.paths = paths

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
        self.paths = CloudPaths(self)
        self.sems = CloudSemaphores(self.paths)
        self.cfg = self._read_cfg()

    def _read_cfg_old(self):
        # support reading the old ConfigObj format file and merging
        # it into the yaml dictionary
        try:
            from configobj import ConfigObj
        except ImportError:
            ConfigObj = None
        if not ConfigObj:
            return {}
        old_cfg = ConfigObj(self.paths.old_config_fn)
        return dict(old_cfg)

    def read_cfg(self):
        if not self.cfg:
            self.cfg = self._read_cfg()
        return self.cfg

    def _read_cfg(self):
        starting_config = get_builtin_cfg()
        try:
            conf = get_base_cfg(self.paths.config, starting_config)
        except Exception:
            conf = starting_config
        old_conf = self._read_cfg_old()
        conf = util.mergedict(conf, old_conf)
        return conf
    
    def restore_from_cache(self):
        pickled_fn = self.paths.get_ipath_cur('obj_pkl')
        try:
            # we try to restore from a current link and static path
            # by using the instance link, if purge_cache was called
            # the file wont exist
            self.datasource = pickle.loads(util.load_file(pickled_fn))
            return True
        except Exception as e:
            LOG.debug("Failed loading pickled datasource from %s due to %s", pickled_fn, e)
            return False
    
    def write_to_cache(self):
        pickled_fn = self.paths.get_ipath_cur("obj_pkl")
        try:
            contents = pickle.dumps(self.datasource)
            util.write_file(pickled_fn, contents, mode=0400)
        except Exception as e:
            LOG.debug("Failed pickling datasource to %s due to %s", pickled_fn, e)
            return False
    
    def get_data_source(self):
        if self.datasource:
            return True
        if self.restore_from_cache():
            LOG.debug("Restored from cache datasource: %s" % self.datasource)
            return True
        (ds, dsname) = sources.find_source(self.cfg, self.ds_deps)
        LOG.debug("Loaded datasource %s:%s", dsname, ds)
        self.datasource = ds
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
        data = CloudPartData(self.datasource, self.paths)

        # This keeps track of all the active handlers
        handlers = CloudHandlers(self)

        # Add handlers in cdir
        for fname in glob.glob(os.path.join(cdir, "*.py")):
            if not os.path.isfile(fname):
                continue
            modname = os.path.basename(fname)[0:-3]
            try:
                mod = parts.fixup_module(importer.import_module(modname))
                types = handlers.register(mod)
                LOG.debug("Added handler for [%s] from %s", types, fname)
            except:
                LOG.exception("Failed to register handler in %s", fname)

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
        user_data.walk(data.get_userdata(), parts.walker_callback, data=part_data)

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
            def_handlers.append(parts.CloudConfigPartHandler(self.paths.get_ipath("cloud_config")))
        if self.paths.get_ipath_cur('scripts'):
            def_handlers.append(parts.ShellScriptPartHandler(self.paths.get_ipath_cur('scripts')))
        if self.paths.get_ipath("boothooks"):
            def_handlers.append(parts.BootHookPartHandler(self.paths.get_ipath("boothooks")))
        if self.paths.upstart_conf_d:
            def_handlers.append(parts.UpstartJobPartHandler(self.paths.upstart_conf_d))
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
    cfgfile = None
    cfg = None

    def __init__(self, cfgfile, cloud=None, ds_deps=None):
        if cloud == None:
            self.cloud = cloudinit.CloudInit(ds_deps)
            self.cloud.get_data_source()
        else:
            self.cloud = cloud
        self.cfg = self.get_config_obj(cfgfile)

    def get_config_obj(self, cfgfile):
        try:
            cfg = util.read_conf(cfgfile)
        except:
            # TODO: this 'log' could/should be passed in
            cloudinit.log.critical("Failed loading of cloud config '%s'. "
                                   "Continuing with empty config\n" % cfgfile)
            cloudinit.log.debug(traceback.format_exc() + "\n")
            cfg = None
        if cfg is None:
            cfg = {}

        try:
            ds_cfg = self.cloud.datasource.get_config_obj()
        except:
            ds_cfg = {}

        cfg = util.mergedict(cfg, ds_cfg)
        return(util.mergedict(cfg, self.cloud.cfg))

    def handle(self, name, args, freq=None):
        try:
            mod = __import__("cc_" + name.replace("-", "_"), globals())
            def_freq = getattr(mod, "frequency", per_instance)
            handler = getattr(mod, "handle")

            if not freq:
                freq = def_freq

            self.cloud.sem_and_run("config-" + name, freq, handler,
                [name, self.cfg, self.cloud, cloudinit.log, args])
        except:
            raise
