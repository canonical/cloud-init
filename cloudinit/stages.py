# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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

from cloudinit.settings import (PER_INSTANCE, FREQUENCIES, CLOUD_CONFIG)

from cloudinit import handlers

# Default handlers (used if not overridden)
from cloudinit.handlers import boot_hook as bh_part
from cloudinit.handlers import cloud_config as cc_part
from cloudinit.handlers import shell_script as ss_part
from cloudinit.handlers import upstart_job as up_part

from cloudinit import cloud
from cloudinit import config
from cloudinit import distros
from cloudinit import helpers
from cloudinit import importer
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import type_utils
from cloudinit import util

LOG = logging.getLogger(__name__)

NULL_DATA_SOURCE = None


class Init(object):
    def __init__(self, ds_deps=None):
        if ds_deps is not None:
            self.ds_deps = ds_deps
        else:
            self.ds_deps = [sources.DEP_FILESYSTEM, sources.DEP_NETWORK]
        # Created on first use
        self._cfg = None
        self._paths = None
        self._distro = None
        # Changed only when a fetch occurs
        self.datasource = NULL_DATA_SOURCE

    def _reset(self, reset_ds=False):
        # Recreated on access
        self._cfg = None
        self._paths = None
        self._distro = None
        if reset_ds:
            self.datasource = NULL_DATA_SOURCE

    @property
    def distro(self):
        if not self._distro:
            # Try to find the right class to use
            system_config = self._extract_cfg('system')
            distro_name = system_config.pop('distro', 'ubuntu')
            distro_cls = distros.fetch(distro_name)
            LOG.debug("Using distro class %s", distro_cls)
            self._distro = distro_cls(distro_name, system_config, self.paths)
            # If we have an active datasource we need to adjust
            # said datasource and move its distro/system config
            # from whatever it was to a new set...
            if self.datasource is not NULL_DATA_SOURCE:
                self.datasource.distro = self._distro
                self.datasource.sys_cfg = system_config
        return self._distro

    @property
    def cfg(self):
        return self._extract_cfg('restricted')

    def _extract_cfg(self, restriction):
        # Ensure actually read
        self.read_cfg()
        # Nobody gets the real config
        ocfg = copy.deepcopy(self._cfg)
        if restriction == 'restricted':
            ocfg.pop('system_info', None)
        elif restriction == 'system':
            ocfg = util.get_cfg_by_path(ocfg, ('system_info',), {})
        elif restriction == 'paths':
            ocfg = util.get_cfg_by_path(ocfg, ('system_info', 'paths'), {})
        if not isinstance(ocfg, (dict)):
            ocfg = {}
        return ocfg

    @property
    def paths(self):
        if not self._paths:
            path_info = self._extract_cfg('paths')
            self._paths = helpers.Paths(path_info, self.datasource)
        return self._paths

    def _initial_subdirs(self):
        c_dir = self.paths.cloud_dir
        initial_dirs = [
            c_dir,
            os.path.join(c_dir, 'scripts'),
            os.path.join(c_dir, 'scripts', 'per-instance'),
            os.path.join(c_dir, 'scripts', 'per-once'),
            os.path.join(c_dir, 'scripts', 'per-boot'),
            os.path.join(c_dir, 'scripts', 'vendor'),
            os.path.join(c_dir, 'seed'),
            os.path.join(c_dir, 'instances'),
            os.path.join(c_dir, 'handlers'),
            os.path.join(c_dir, 'sem'),
            os.path.join(c_dir, 'data'),
        ]
        return initial_dirs

    def purge_cache(self, rm_instance_lnk=True):
        rm_list = []
        rm_list.append(self.paths.boot_finished)
        if rm_instance_lnk:
            rm_list.append(self.paths.instance_link)
        for f in rm_list:
            util.del_file(f)
        return len(rm_list)

    def initialize(self):
        self._initialize_filesystem()

    def _initialize_filesystem(self):
        util.ensure_dirs(self._initial_subdirs())
        log_file = util.get_cfg_option_str(self.cfg, 'def_log_file')
        perms = util.get_cfg_option_str(self.cfg, 'syslog_fix_perms')
        if log_file:
            util.ensure_file(log_file)
            if perms:
                u, g = util.extract_usergroup(perms)
                try:
                    util.chownbyname(log_file, u, g)
                except OSError:
                    util.logexc(LOG, "Unable to change the ownership of %s to "
                                "user %s, group %s", log_file, u, g)

    def read_cfg(self, extra_fns=None):
        # None check so that we don't keep on re-loading if empty
        if self._cfg is None:
            self._cfg = self._read_cfg(extra_fns)
            # LOG.debug("Loaded 'init' config %s", self._cfg)

    def _read_cfg(self, extra_fns):
        no_cfg_paths = helpers.Paths({}, self.datasource)
        merger = helpers.ConfigMerger(paths=no_cfg_paths,
                                      datasource=self.datasource,
                                      additional_fns=extra_fns,
                                      base_cfg=fetch_base_config())
        return merger.cfg

    def _restore_from_cache(self):
        # We try to restore from a current link and static path
        # by using the instance link, if purge_cache was called
        # the file wont exist.
        pickled_fn = self.paths.get_ipath_cur('obj_pkl')
        pickle_contents = None
        try:
            pickle_contents = util.load_file(pickled_fn)
        except Exception:
            pass
        # This is expected so just return nothing
        # successfully loaded...
        if not pickle_contents:
            return None
        try:
            return pickle.loads(pickle_contents)
        except Exception:
            util.logexc(LOG, "Failed loading pickled blob from %s", pickled_fn)
            return None

    def _write_to_cache(self):
        if self.datasource is NULL_DATA_SOURCE:
            return False
        pickled_fn = self.paths.get_ipath_cur("obj_pkl")
        try:
            pk_contents = pickle.dumps(self.datasource)
        except Exception:
            util.logexc(LOG, "Failed pickling datasource %s", self.datasource)
            return False
        try:
            util.write_file(pickled_fn, pk_contents, mode=0400)
        except Exception:
            util.logexc(LOG, "Failed pickling datasource to %s", pickled_fn)
            return False
        return True

    def _get_datasources(self):
        # Any config provided???
        pkg_list = self.cfg.get('datasource_pkg_list') or []
        # Add the defaults at the end
        for n in ['', type_utils.obj_name(sources)]:
            if n not in pkg_list:
                pkg_list.append(n)
        cfg_list = self.cfg.get('datasource_list') or []
        return (cfg_list, pkg_list)

    def _get_data_source(self):
        if self.datasource is not NULL_DATA_SOURCE:
            return self.datasource
        ds = self._restore_from_cache()
        if ds:
            LOG.debug("Restored from cache, datasource: %s", ds)
        if not ds:
            (cfg_list, pkg_list) = self._get_datasources()
            # Deep copy so that user-data handlers can not modify
            # (which will affect user-data handlers down the line...)
            (ds, dsname) = sources.find_source(self.cfg,
                                               self.distro,
                                               self.paths,
                                               copy.deepcopy(self.ds_deps),
                                               cfg_list,
                                               pkg_list)
            LOG.info("Loaded datasource %s - %s", dsname, ds)
        self.datasource = ds
        # Ensure we adjust our path members datasource
        # now that we have one (thus allowing ipath to be used)
        self._reset()
        return ds

    def _get_instance_subdirs(self):
        return ['handlers', 'scripts', 'sem']

    def _get_ipath(self, subname=None):
        # Force a check to see if anything
        # actually comes back, if not
        # then a datasource has not been assigned...
        instance_dir = self.paths.get_ipath(subname)
        if not instance_dir:
            raise RuntimeError(("No instance directory is available."
                                " Has a datasource been fetched??"))
        return instance_dir

    def _reflect_cur_instance(self):
        # Remove the old symlink and attach a new one so
        # that further reads/writes connect into the right location
        idir = self._get_ipath()
        util.del_file(self.paths.instance_link)
        util.sym_link(idir, self.paths.instance_link)

        # Ensures these dirs exist
        dir_list = []
        for d in self._get_instance_subdirs():
            dir_list.append(os.path.join(idir, d))
        util.ensure_dirs(dir_list)

        # Write out information on what is being used for the current instance
        # and what may have been used for a previous instance...
        dp = self.paths.get_cpath('data')

        # Write what the datasource was and is..
        ds = "%s: %s" % (type_utils.obj_name(self.datasource), self.datasource)
        previous_ds = None
        ds_fn = os.path.join(idir, 'datasource')
        try:
            previous_ds = util.load_file(ds_fn).strip()
        except Exception:
            pass
        if not previous_ds:
            previous_ds = ds
        util.write_file(ds_fn, "%s\n" % ds)
        util.write_file(os.path.join(dp, 'previous-datasource'),
                        "%s\n" % (previous_ds))

        # What the instance id was and is...
        iid = self.datasource.get_instance_id()
        previous_iid = None
        iid_fn = os.path.join(dp, 'instance-id')
        try:
            previous_iid = util.load_file(iid_fn).strip()
        except Exception:
            pass
        if not previous_iid:
            previous_iid = iid
        util.write_file(iid_fn, "%s\n" % iid)
        util.write_file(os.path.join(dp, 'previous-instance-id'),
                        "%s\n" % (previous_iid))
        # Ensure needed components are regenerated
        # after change of instance which may cause
        # change of configuration
        self._reset()
        return iid

    def fetch(self):
        return self._get_data_source()

    def instancify(self):
        return self._reflect_cur_instance()

    def cloudify(self):
        # Form the needed options to cloudify our members
        return cloud.Cloud(self.datasource,
                           self.paths, self.cfg,
                           self.distro, helpers.Runners(self.paths))

    def update(self):
        if not self._write_to_cache():
            return
        self._store_userdata()
        self._store_vendordata()

    def _store_userdata(self):
        raw_ud = "%s" % (self.datasource.get_userdata_raw())
        util.write_file(self._get_ipath('userdata_raw'), raw_ud, 0600)
        processed_ud = "%s" % (self.datasource.get_userdata())
        util.write_file(self._get_ipath('userdata'), processed_ud, 0600)

    def _store_vendordata(self):
        raw_vd = "%s" % (self.datasource.get_vendordata_raw())
        util.write_file(self._get_ipath('vendordata_raw'), raw_vd, 0600)
        processed_vd = "%s" % (self.datasource.get_vendordata())
        util.write_file(self._get_ipath('vendordata'), processed_vd, 0600)

    def _default_handlers(self, opts=None):
        if opts is None:
            opts = {}

        opts.update({
            'paths': self.paths,
            'datasource': self.datasource,
        })
        # TODO(harlowja) Hmmm, should we dynamically import these??
        def_handlers = [
            cc_part.CloudConfigPartHandler(**opts),
            ss_part.ShellScriptPartHandler(**opts),
            bh_part.BootHookPartHandler(**opts),
            up_part.UpstartJobPartHandler(**opts),
        ]
        return def_handlers

    def _default_userdata_handlers(self):
        return self._default_handlers()

    def _default_vendordata_handlers(self):
        return self._default_handlers(
            opts={'script_path': 'vendor_scripts',
                  'cloud_config_path': 'vendor_cloud_config'})

    def _do_handlers(self, data_msg, c_handlers_list, frequency,
                     excluded=None):
        """
        Generalized handlers suitable for use with either vendordata
        or userdata
        """
        if excluded is None:
            excluded = []

        cdir = self.paths.get_cpath("handlers")
        idir = self._get_ipath("handlers")

        # Add the path to the plugins dir to the top of our list for importing
        # new handlers.
        #
        # Note(harlowja): instance dir should be read before cloud-dir
        for d in [cdir, idir]:
            if d and d not in sys.path:
                sys.path.insert(0, d)

        def register_handlers_in_dir(path):
            # Attempts to register any handler modules under the given path.
            if not path or not os.path.isdir(path):
                return
            potential_handlers = util.find_modules(path)
            for (fname, mod_name) in potential_handlers.iteritems():
                try:
                    mod_locs, looked_locs = importer.find_module(
                        mod_name, [''], ['list_types', 'handle_part'])
                    if not mod_locs:
                        LOG.warn("Could not find a valid user-data handler"
                                 " named %s in file %s (searched %s)",
                                 mod_name, fname, looked_locs)
                        continue
                    mod = importer.import_module(mod_locs[0])
                    mod = handlers.fixup_handler(mod)
                    types = c_handlers.register(mod)
                    if types:
                        LOG.debug("Added custom handler for %s [%s] from %s",
                                  types, mod, fname)
                except Exception:
                    util.logexc(LOG, "Failed to register handler from %s",
                                fname)

        # This keeps track of all the active handlers
        c_handlers = helpers.ContentHandlers()

        # Add any handlers in the cloud-dir
        register_handlers_in_dir(cdir)

        # Register any other handlers that come from the default set. This
        # is done after the cloud-dir handlers so that the cdir modules can
        # take over the default user-data handler content-types.
        for mod in c_handlers_list:
            types = c_handlers.register(mod, overwrite=False)
            if types:
                LOG.debug("Added default handler for %s from %s", types, mod)

        # Form our cloud interface
        data = self.cloudify()

        def init_handlers():
            # Init the handlers first
            for (_ctype, mod) in c_handlers.iteritems():
                if mod in c_handlers.initialized:
                    # Avoid initing the same module twice (if said module
                    # is registered to more than one content-type).
                    continue
                handlers.call_begin(mod, data, frequency)
                c_handlers.initialized.append(mod)

        def walk_handlers(excluded):
            # Walk the user data
            part_data = {
                'handlers': c_handlers,
                # Any new handlers that are encountered get writen here
                'handlerdir': idir,
                'data': data,
                # The default frequency if handlers don't have one
                'frequency': frequency,
                # This will be used when new handlers are found
                # to help write there contents to files with numbered
                # names...
                'handlercount': 0,
                'excluded': excluded,
            }
            handlers.walk(data_msg, handlers.walker_callback, data=part_data)

        def finalize_handlers():
            # Give callbacks opportunity to finalize
            for (_ctype, mod) in c_handlers.iteritems():
                if mod not in c_handlers.initialized:
                    # Said module was never inited in the first place, so lets
                    # not attempt to finalize those that never got called.
                    continue
                c_handlers.initialized.remove(mod)
                try:
                    handlers.call_end(mod, data, frequency)
                except:
                    util.logexc(LOG, "Failed to finalize handler: %s", mod)

        try:
            init_handlers()
            walk_handlers(excluded)
        finally:
            finalize_handlers()

    def consume_data(self, frequency=PER_INSTANCE):
        # Consume the userdata first, because we need want to let the part
        # handlers run first (for merging stuff)
        self._consume_userdata(frequency)
        self._consume_vendordata(frequency)

        # Perform post-consumption adjustments so that
        # modules that run during the init stage reflect
        # this consumed set.
        #
        # They will be recreated on future access...
        self._reset()
        # Note(harlowja): the 'active' datasource will have
        # references to the previous config, distro, paths
        # objects before the load of the userdata happened,
        # this is expected.

    def _consume_vendordata(self, frequency=PER_INSTANCE):
        """
        Consume the vendordata and run the part handlers on it
        """
        # User-data should have been consumed first.
        # So we merge the other available cloud-configs (everything except
        # vendor provided), and check whether or not we should consume
        # vendor data at all. That gives user or system a chance to override.
        if not self.datasource.get_vendordata_raw():
            LOG.debug("no vendordata from datasource")
            return

        _cc_merger = helpers.ConfigMerger(paths=self._paths,
                                          datasource=self.datasource,
                                          additional_fns=[],
                                          base_cfg=self.cfg,
                                          include_vendor=False)
        vdcfg = _cc_merger.cfg.get('vendor_data', {})

        if not isinstance(vdcfg, dict):
            vdcfg = {'enabled': False}
            LOG.warn("invalid 'vendor_data' setting. resetting to: %s", vdcfg)

        enabled = vdcfg.get('enabled')
        no_handlers = vdcfg.get('disabled_handlers', None)

        if not util.is_true(enabled):
            LOG.debug("vendordata consumption is disabled.")
            return

        LOG.debug("vendor data will be consumed. disabled_handlers=%s",
                  no_handlers)

        # Ensure vendordata source fetched before activation (just incase)
        vendor_data_msg = self.datasource.get_vendordata()

        # This keeps track of all the active handlers, while excluding what the
        # users doesn't want run, i.e. boot_hook, cloud_config, shell_script
        c_handlers_list = self._default_vendordata_handlers()

        # Run the handlers
        self._do_handlers(vendor_data_msg, c_handlers_list, frequency,
                          excluded=no_handlers)

    def _consume_userdata(self, frequency=PER_INSTANCE):
        """
        Consume the userdata and run the part handlers
        """

        # Ensure datasource fetched before activation (just incase)
        user_data_msg = self.datasource.get_userdata(True)

        # This keeps track of all the active handlers
        c_handlers_list = self._default_handlers()

        # Run the handlers
        self._do_handlers(user_data_msg, c_handlers_list, frequency)


class Modules(object):
    def __init__(self, init, cfg_files=None):
        self.init = init
        self.cfg_files = cfg_files
        # Created on first use
        self._cached_cfg = None

    @property
    def cfg(self):
        # None check to avoid empty case causing re-reading
        if self._cached_cfg is None:
            merger = helpers.ConfigMerger(paths=self.init.paths,
                                          datasource=self.init.datasource,
                                          additional_fns=self.cfg_files,
                                          base_cfg=self.init.cfg)
            self._cached_cfg = merger.cfg
            # LOG.debug("Loading 'module' config %s", self._cached_cfg)
        # Only give out a copy so that others can't modify this...
        return copy.deepcopy(self._cached_cfg)

    def _read_modules(self, name):
        module_list = []
        if name not in self.cfg:
            return module_list
        cfg_mods = self.cfg[name]
        # Create 'module_list', an array of hashes
        # Where hash['mod'] = module name
        #       hash['freq'] = frequency
        #       hash['args'] = arguments
        for item in cfg_mods:
            if not item:
                continue
            if isinstance(item, (str, basestring)):
                module_list.append({
                    'mod': item.strip(),
                })
            elif isinstance(item, (list)):
                contents = {}
                # Meant to fall through...
                if len(item) >= 1:
                    contents['mod'] = item[0].strip()
                if len(item) >= 2:
                    contents['freq'] = item[1].strip()
                if len(item) >= 3:
                    contents['args'] = item[2:]
                if contents:
                    module_list.append(contents)
            elif isinstance(item, (dict)):
                contents = {}
                valid = False
                if 'name' in item:
                    contents['mod'] = item['name'].strip()
                    valid = True
                if 'frequency' in item:
                    contents['freq'] = item['frequency'].strip()
                if 'args' in item:
                    contents['args'] = item['args'] or []
                if contents and valid:
                    module_list.append(contents)
            else:
                raise TypeError(("Failed to read '%s' item in config,"
                                 " unknown type %s") %
                                 (item, type_utils.obj_name(item)))
        return module_list

    def _fixup_modules(self, raw_mods):
        mostly_mods = []
        for raw_mod in raw_mods:
            raw_name = raw_mod['mod']
            freq = raw_mod.get('freq')
            run_args = raw_mod.get('args') or []
            mod_name = config.form_module_name(raw_name)
            if not mod_name:
                continue
            if freq and freq not in FREQUENCIES:
                LOG.warn(("Config specified module %s"
                          " has an unknown frequency %s"), raw_name, freq)
                # Reset it so when ran it will get set to a known value
                freq = None
            mod_locs, looked_locs = importer.find_module(
                mod_name, ['', type_utils.obj_name(config)], ['handle'])
            if not mod_locs:
                LOG.warn("Could not find module named %s (searched %s)",
                         mod_name, looked_locs)
                continue
            mod = config.fixup_module(importer.import_module(mod_locs[0]))
            mostly_mods.append([mod, raw_name, freq, run_args])
        return mostly_mods

    def _run_modules(self, mostly_mods):
        cc = self.init.cloudify()
        # Return which ones ran
        # and which ones failed + the exception of why it failed
        failures = []
        which_ran = []
        for (mod, name, freq, args) in mostly_mods:
            try:
                # Try the modules frequency, otherwise fallback to a known one
                if not freq:
                    freq = mod.frequency
                if freq not in FREQUENCIES:
                    freq = PER_INSTANCE
                LOG.debug("Running module %s (%s) with frequency %s",
                          name, mod, freq)

                # Use the configs logger and not our own
                # TODO(harlowja): possibly check the module
                # for having a LOG attr and just give it back
                # its own logger?
                func_args = [name, self.cfg,
                             cc, config.LOG, args]
                # Mark it as having started running
                which_ran.append(name)
                # This name will affect the semaphore name created
                run_name = "config-%s" % (name)
                cc.run(run_name, mod.handle, func_args, freq=freq)
            except Exception as e:
                util.logexc(LOG, "Running module %s (%s) failed", name, mod)
                failures.append((name, e))
        return (which_ran, failures)

    def run_single(self, mod_name, args=None, freq=None):
        # Form the users module 'specs'
        mod_to_be = {
            'mod': mod_name,
            'args': args,
            'freq': freq,
        }
        # Now resume doing the normal fixups and running
        raw_mods = [mod_to_be]
        mostly_mods = self._fixup_modules(raw_mods)
        return self._run_modules(mostly_mods)

    def run_section(self, section_name):
        raw_mods = self._read_modules(section_name)
        mostly_mods = self._fixup_modules(raw_mods)
        d_name = self.init.distro.name

        skipped = []
        forced = []
        overridden = self.cfg.get('unverified_modules', [])
        for (mod, name, _freq, _args) in mostly_mods:
            worked_distros = set(mod.distros)
            worked_distros.update(
                distros.Distro.expand_osfamily(mod.osfamilies))

            # module does not declare 'distros' or lists this distro
            if not worked_distros or d_name in worked_distros:
                continue

            if name in overridden:
                forced.append(name)
            else:
                skipped.append(name)

        if skipped:
            LOG.info("Skipping modules %s because they are not verified "
                      "on distro '%s'.  To run anyway, add them to "
                      "'unverified_modules' in config.", skipped, d_name)
        if forced:
            LOG.info("running unverified_modules: %s", forced)

        return self._run_modules(mostly_mods)


def fetch_base_config():
    base_cfgs = []
    default_cfg = util.get_builtin_cfg()
    kern_contents = util.read_cc_from_cmdline()

    # Kernel/cmdline parameters override system config
    if kern_contents:
        base_cfgs.append(util.load_yaml(kern_contents, default={}))

    # Anything in your conf.d location??
    # or the 'default' cloud.cfg location???
    base_cfgs.append(util.read_conf_with_confd(CLOUD_CONFIG))

    # And finally the default gets to play
    if default_cfg:
        base_cfgs.append(default_cfg)

    return util.mergemanydict(base_cfgs)
