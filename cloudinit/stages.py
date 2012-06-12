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

import cPickle as pickle

import copy
import os
import sys

try:
    from configobj import ConfigObj
except ImportError:
    ConfigObj = None

from cloudinit.settings import (PER_INSTANCE)
from cloudinit.settings import (OLD_CLOUD_CONFIG)

from cloudinit import cloud
from cloudinit import distros
from cloudinit import handlers
from cloudinit import helpers
from cloudinit import importer
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import util

from cloudinit import user_data as ud

LOG = logging.getLogger(__name__)


class Init(object):
    def __init__(self, ds_deps=None):
        self.datasource = None
        if ds_deps:
            self.ds_deps = ds_deps
        else:
            self.ds_deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
        # Created on first use
        self.cached_cfg = None
        self.cached_distro = None
        self.cached_paths = None

    def _read_cfg_old(self):
        # Support reading the old ConfigObj format file and merging
        # it into the yaml dictionary
        if not ConfigObj:
            return {}
        old_cfg = ConfigObj(OLD_CLOUD_CONFIG)
        return dict(old_cfg)

    @property
    def cfg(self):
        if self.cached_cfg is None:
            self.cached_cfg = self._read_cfg()
        return self.cached_cfg

    @property
    def paths(self):
        if not self.cached_paths:
            sys_info = self.cfg.get('system_info', {})
            self.cached_paths = helpers.Paths(copy.deepcopy(sys_info),
                                          self.datasource)
        return self.cached_paths

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
            util.del_file(f)
        return len(rmlist)

    def initialize(self):
        self._initialize_filesystem()

    def _initialize_filesystem(self):
        util.ensure_dirs(self._initial_subdirs())
        log_file = util.get_cfg_option_str(self.cfg, 'def_log_file')
        perms = util.get_cfg_option_str(self.cfg, 'syslog_fix_perms')
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
        b_config = util.get_builtin_cfg()
        try:
            conf = util.get_base_cfg()
        except Exception:
            conf = b_config
        return util.mergedict(conf, self._read_cfg_old())

    def _restore_from_cache(self):
        pickled_fn = self.paths.get_ipath_cur('obj_pkl')
        try:
            # we try to restore from a current link and static path
            # by using the instance link, if purge_cache was called
            # the file wont exist
            return pickle.loads(util.load_file(pickled_fn))
        except Exception as e:
            LOG.exception(("Failed loading pickled datasource from"
                           " %s due to: %s"), pickled_fn, e)
            return None

    def _write_to_cache(self):
        pickled_fn = self.paths.get_ipath_cur("obj_pkl")
        try:
            contents = pickle.dumps(self.datasource)
            util.write_file(pickled_fn, contents, mode=0400)
        except Exception as e:
            LOG.exception(("Failed pickling datasource to"
                          " %s due to: %s"), pickled_fn, e)
            return False

    def _get_datasources(self):
        # Any config provided???
        pkg_list = self.cfg.get('datasource_pkg_list') or []
        # Add the defaults at the end
        for n in [util.obj_name(sources), '']:
            if n not in pkg_list:
                pkg_list.append(n)
        cfg_list = self.cfg.get('datasource_list') or []
        return (cfg_list, pkg_list)

    def _get_data_source(self):
        if self.datasource:
            return self.datasource
        ds = self._restore_from_cache()
        if ds:
            LOG.debug("Restored from cache datasource: %s" % ds)
        else:
            (cfg_list, pkg_list) = self._get_datasources()
            # Deep copy so that handlers can not modify (which will
            # affect handlers down the line...)
            sys_cfg = copy.deepcopy(self.cfg)
            ds_deps = copy.deepcopy(self.ds_deps)
            distro = distros.fetch(sys_cfg,
                                   cloud.Cloud(self.datasource,
                                               self.paths, sys_cfg))
            (ds, dsname) = sources.find_source(sys_cfg, distro, self.paths,
                                               ds_deps, cfg_list, pkg_list)
            LOG.debug("Loaded datasource %s - %s", dsname, ds)
        self.datasource = ds
        if self.cached_paths:
            self.cached_paths.datasource = ds
        return ds

    def _reflect_cur_instance(self):
        # Ensure we are hooked into the right symlink for the current instance
        idir = self.paths.get_ipath()
        util.del_file(self.paths.instance_link)
        util.sym_link(idir, self.paths.instance_link)

        # Ensures these dirs exist
        dir_list = []
        for d in ["handlers", "scripts", "sem"]:
            dir_list.append(os.path.join(idir, d))
        util.ensure_dirs(dir_list)

        # Write out information on what is being used for the current instance
        # and what may have been used for a previous instance...
        dp = self.paths.get_cpath('data')

        # Write what the datasource was and is..
        ds = "%s: %s" % (util.obj_name(self.datasource), self.datasource)
        previous_ds = ''
        ds_fn = os.path.join(idir, 'datasource')
        try:
            previous_ds = util.load_file(ds_fn).strip()
        except Exception:
            pass
        if not previous_ds:
            # TODO: ?? is this right
            previous_ds = ds
        util.write_file(ds_fn, "%s\n" % ds)
        util.write_file(os.path.join(dp, 'previous-datasource'),
                        "%s\n" % (previous_ds))

        # What the instance id was and is...
        iid = self.datasource.get_instance_id()
        previous_iid = ''
        p_iid_fn = os.path.join(dp, 'previous-instance-id')
        c_iid_fn = os.path.join(dp, 'instance-id')
        try:
            previous_iid = util.load_file(p_iid_fn).strip()
        except Exception:
            pass
        if not previous_iid:
            # TODO: ?? is this right
            previous_iid = iid
        util.write_file(c_iid_fn, "%s\n" % iid)
        util.write_file(p_iid_fn, "%s\n" % previous_iid)

    def fetch(self):
        return self._get_data_source()

    def instancify(self):
        self._reflect_cur_instance()

    def update(self):
        self._write_to_cache()
        self._store_userdata()

    def _store_userdata(self):
        raw_ud = "%s" % (self.datasource.get_userdata_raw())
        util.write_file(self.paths.get_ipath('userdata_raw'), raw_ud, 0600)
        processed_ud = "%s" % (self.datasource.get_userdata())
        util.write_file(self.paths.get_ipath('userdata'), processed_ud, 0600)

    def consume(self, frequency=PER_INSTANCE):
        cdir = self.paths.get_cpath("handlers")
        idir = self.paths.get_ipath("handlers")
    
        # Add the path to the plugins dir to the top of our list for import
        # instance dir should be read before cloud-dir
        sys.path.insert(0, cdir)
        sys.path.insert(0, idir)

        # This keeps track of all the active handlers
        c_handlers = helpers.ContentHandlers(self.paths)

        # Add handlers in cdir
        potential_handlers = util.find_modules(cdir)
        for (fname, modname) in potential_handlers.iteritems():
            try:
                mod = ud.fixup_module(importer.import_module(modname))
                types = c_handlers.register(mod)
                LOG.debug("Added handler for [%s] from %s", types, fname)
            except:
                LOG.exception("Failed to register handler from %s", fname)

        def_handlers = c_handlers.register_defaults()
        if def_handlers:
            LOG.debug("Registered default handlers for [%s]", def_handlers)

        # Form our cloud proxy
        data = cloud.Cloud(self.datasource,
                           self.paths, copy.deepcopy(self.cfg))

        # Ensure userdata fetched before activation
        ud_obj = data.get_userdata()

        # Init the handlers first
        called = []
        for (_mtype, mod) in c_handlers.iteritems():
            if mod in called:
                continue
            ud.call_begin(mod, data, frequency)
            called.append(mod)

        # Walk the user data
        part_data = {
            'handlers': c_handlers,
            'handlerdir': idir,
            'data': data, 
            'frequency': frequency,
            # This will be used when new handlers are found
            # to help write there contents to files with numbered
            # names...
            'handlercount': 0,
        }
        ud.walk(ud_obj, ud.walker_callback, data=part_data)

        # Give callbacks opportunity to finalize
        called = []
        for (_mtype, mod) in c_handlers.iteritems():
            if mod in called:
                continue
            ud.call_end(mod, data, frequency)
            called.append(mod)


class Handlers(object):
    def __init__(self, datasource, h_cloud, cfgfile=None, basecfg=None):
        self.datasource = datasource
        self.cfgfile = cfgfile
        self.basecfg = basecfg
        self.h_cloud = h_cloud
        self.cachedcfg = None

    @property
    def cfg(self):
        if self.cachedcfg is None:
            self.cachedcfg = self._get_config(self.cfgfile)
        return self.cachedcfg

    def _get_config(self, cfgfile):
        mcfg = None

        if self.cfgfile:
            try:
                mcfg = util.read_conf(cfgfile)
            except:
                LOG.exception(("Failed loading of cloud config '%s'. "
                              "Continuing with an empty config."), cfgfile)
        if not mcfg:
            mcfg = {}

        ds_cfg = None
        try:
            ds_cfg = self.datasource.get_config_obj()
        except:
            LOG.exception("Failed loading of datasource config.")
        if not ds_cfg:
            ds_cfg = {}

        mcfg = util.mergedict(mcfg, ds_cfg)
        if self.basecfg:
            return util.mergedict(mcfg, self.basecfg)
        else:
            return mcfg


    def _read_modules(self, name):
        module_list = []
        if name not in self.cfg:
            return module_list
        cfg_mods = self.cfg[name]
        # Create 'module_list', an array of arrays
        # Where array[0] = module name
        #       array[1] = frequency
        #       array[2:] = arguments
        for item in cfg_mods:
            if not item:
                continue
            if isinstance(item, str):
                module_list.append([item])
            elif isinstance(item, list):
                module_list.append(item)
            else:
                raise TypeError("Failed to read '%s' item in config")
        return module_list

    def _form_modules(self, raw_mods):
        mostly_mods = []
        for raw_mod in raw_mods:
            raw_name = raw_mod[0]
            freq = None
            run_args = None
            if len(raw_mod) > 1:
                freq = raw_mod[1]
            if len(raw_mod) > 2:
                run_args = raw_mod[2:]
            if not run_args:
                run_args = []
            mod_name = handlers.form_module_name(raw_name)
            if not mod_name:
                continue
            mod = handlers.fixup_module(importer.import_module(mod_name))
            mostly_mods.append([mod, raw_name, freq, run_args])
        return mostly_mods

    def _run_modules(self, mostly_mods):
        failures = []
        for (mod, name, freq, args) in mostly_mods:
            try:
                if not freq:
                    freq = mod.frequency
                if not freq:
                    freq = PER_INSTANCE
                func_args = [name, copy.deepcopy(self.cfg),
                             self.h_cloud, LOG,
                             args]
                run_name = "config-" + name        
                self.h_cloud.run(run_name, mod.handle, func_args, freq=freq)
            except:
                LOG.exception("Running %s failed", mod)
                failures.append(name)
        return failures

    def run(self, name):
        raw_mods = self._read_modules(name)
        mostly_mods = self._form_modules(raw_mods)
        return self._run_modules(mostly_mods)
