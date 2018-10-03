# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from time import time

import contextlib
import os

from six import StringIO
from six.moves.configparser import (
    NoSectionError, NoOptionError, RawConfigParser)

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS, PER_ONCE,
                                CFG_ENV_NAME)

from cloudinit import log as logging
from cloudinit import type_utils
from cloudinit import util

LOG = logging.getLogger(__name__)


class LockFailure(Exception):
    pass


class DummyLock(object):
    pass


class DummySemaphores(object):
    def __init__(self):
        pass

    @contextlib.contextmanager
    def lock(self, _name, _freq, _clear_on_fail=False):
        yield DummyLock()

    def has_run(self, _name, _freq):
        return False

    def clear(self, _name, _freq):
        return True

    def clear_all(self):
        pass


class FileLock(object):
    def __init__(self, fn):
        self.fn = fn

    def __str__(self):
        return "<%s using file %r>" % (type_utils.obj_name(self), self.fn)


def canon_sem_name(name):
    return name.replace("-", "_")


class FileSemaphores(object):
    def __init__(self, sem_path):
        self.sem_path = sem_path

    @contextlib.contextmanager
    def lock(self, name, freq, clear_on_fail=False):
        name = canon_sem_name(name)
        try:
            yield self._acquire(name, freq)
        except Exception:
            if clear_on_fail:
                self.clear(name, freq)
            raise

    def clear(self, name, freq):
        name = canon_sem_name(name)
        sem_file = self._get_path(name, freq)
        try:
            util.del_file(sem_file)
        except (IOError, OSError):
            util.logexc(LOG, "Failed deleting semaphore %s", sem_file)
            return False
        return True

    def clear_all(self):
        try:
            util.del_dir(self.sem_path)
        except (IOError, OSError):
            util.logexc(LOG, "Failed deleting semaphore directory %s",
                        self.sem_path)

    def _acquire(self, name, freq):
        # Check again if its been already gotten
        if self.has_run(name, freq):
            return None
        # This is a race condition since nothing atomic is happening
        # here, but this should be ok due to the nature of when
        # and where cloud-init runs... (file writing is not a lock...)
        sem_file = self._get_path(name, freq)
        contents = "%s: %s\n" % (os.getpid(), time())
        try:
            util.write_file(sem_file, contents)
        except (IOError, OSError):
            util.logexc(LOG, "Failed writing semaphore file %s", sem_file)
            return None
        return FileLock(sem_file)

    def has_run(self, name, freq):
        if not freq or freq == PER_ALWAYS:
            return False

        cname = canon_sem_name(name)
        sem_file = self._get_path(cname, freq)
        # This isn't really a good atomic check
        # but it suffices for where and when cloudinit runs
        if os.path.exists(sem_file):
            return True

        # this case could happen if the migrator module hadn't run yet
        # but the item had run before we did canon_sem_name.
        if cname != name and os.path.exists(self._get_path(name, freq)):
            LOG.warning("%s has run without canonicalized name [%s].\n"
                        "likely the migrator has not yet run. "
                        "It will run next boot.\n"
                        "run manually with: cloud-init single --name=migrator",
                        name, cname)
            return True

        return False

    def _get_path(self, name, freq):
        sem_path = self.sem_path
        if not freq or freq == PER_INSTANCE:
            return os.path.join(sem_path, name)
        else:
            return os.path.join(sem_path, "%s.%s" % (name, freq))


class Runners(object):
    def __init__(self, paths):
        self.paths = paths
        self.sems = {}

    def _get_sem(self, freq):
        if freq == PER_ALWAYS or not freq:
            return None
        sem_path = None
        if freq == PER_INSTANCE:
            # This may not exist,
            # so thats why we still check for none
            # below if say the paths object
            # doesn't have a datasource that can
            # provide this instance path...
            sem_path = self.paths.get_ipath("sem")
        elif freq == PER_ONCE:
            sem_path = self.paths.get_cpath("sem")
        if not sem_path:
            return None
        if sem_path not in self.sems:
            self.sems[sem_path] = FileSemaphores(sem_path)
        return self.sems[sem_path]

    def run(self, name, functor, args, freq=None, clear_on_fail=False):
        sem = self._get_sem(freq)
        if not sem:
            sem = DummySemaphores()
        if not args:
            args = []
        if sem.has_run(name, freq):
            LOG.debug("%s already ran (freq=%s)", name, freq)
            return (False, None)
        with sem.lock(name, freq, clear_on_fail) as lk:
            if not lk:
                raise LockFailure("Failed to acquire lock for %s" % name)
            else:
                LOG.debug("Running %s using lock (%s)", name, lk)
                if isinstance(args, (dict)):
                    results = functor(**args)
                else:
                    results = functor(*args)
                return (True, results)


class ConfigMerger(object):
    def __init__(self, paths=None, datasource=None,
                 additional_fns=None, base_cfg=None,
                 include_vendor=True):
        self._paths = paths
        self._ds = datasource
        self._fns = additional_fns
        self._base_cfg = base_cfg
        self._include_vendor = include_vendor
        # Created on first use
        self._cfg = None

    def _get_datasource_configs(self):
        d_cfgs = []
        if self._ds:
            try:
                ds_cfg = self._ds.get_config_obj()
                if ds_cfg and isinstance(ds_cfg, (dict)):
                    d_cfgs.append(ds_cfg)
            except Exception:
                util.logexc(LOG, "Failed loading of datasource config object "
                            "from %s", self._ds)
        return d_cfgs

    def _get_env_configs(self):
        e_cfgs = []
        if CFG_ENV_NAME in os.environ:
            e_fn = os.environ[CFG_ENV_NAME]
            try:
                e_cfgs.append(util.read_conf(e_fn))
            except Exception:
                util.logexc(LOG, 'Failed loading of env. config from %s',
                            e_fn)
        return e_cfgs

    def _get_instance_configs(self):
        i_cfgs = []
        # If cloud-config was written, pick it up as
        # a configuration file to use when running...
        if not self._paths:
            return i_cfgs

        cc_paths = ['cloud_config']
        if self._include_vendor:
            cc_paths.append('vendor_cloud_config')

        for cc_p in cc_paths:
            cc_fn = self._paths.get_ipath_cur(cc_p)
            if cc_fn and os.path.isfile(cc_fn):
                try:
                    i_cfgs.append(util.read_conf(cc_fn))
                except PermissionError:
                    LOG.debug(
                        'Skipped loading cloud-config from %s due to'
                        ' non-root.', cc_fn)
                except Exception:
                    util.logexc(LOG, 'Failed loading of cloud-config from %s',
                                cc_fn)
        return i_cfgs

    def _read_cfg(self):
        # Input config files override
        # env config files which
        # override instance configs
        # which override datasource
        # configs which override
        # base configuration
        cfgs = []
        if self._fns:
            for c_fn in self._fns:
                try:
                    cfgs.append(util.read_conf(c_fn))
                except Exception:
                    util.logexc(LOG, "Failed loading of configuration from %s",
                                c_fn)

        cfgs.extend(self._get_env_configs())
        cfgs.extend(self._get_instance_configs())
        cfgs.extend(self._get_datasource_configs())
        if self._base_cfg:
            cfgs.append(self._base_cfg)
        return util.mergemanydict(cfgs)

    @property
    def cfg(self):
        # None check to avoid empty case causing re-reading
        if self._cfg is None:
            self._cfg = self._read_cfg()
        return self._cfg


class ContentHandlers(object):

    def __init__(self):
        self.registered = {}
        self.initialized = []

    def __contains__(self, item):
        return self.is_registered(item)

    def __getitem__(self, key):
        return self._get_handler(key)

    def is_registered(self, content_type):
        return content_type in self.registered

    def register(self, mod, initialized=False, overwrite=True):
        types = set()
        for t in mod.list_types():
            if overwrite:
                types.add(t)
            else:
                if not self.is_registered(t):
                    types.add(t)
        for t in types:
            self.registered[t] = mod
        if initialized and mod not in self.initialized:
            self.initialized.append(mod)
        return types

    def _get_handler(self, content_type):
        return self.registered[content_type]

    def items(self):
        return list(self.registered.items())


class Paths(object):
    def __init__(self, path_cfgs, ds=None):
        self.cfgs = path_cfgs
        # Populate all the initial paths
        self.cloud_dir = path_cfgs.get('cloud_dir', '/var/lib/cloud')
        self.run_dir = path_cfgs.get('run_dir', '/run/cloud-init')
        self.instance_link = os.path.join(self.cloud_dir, 'instance')
        self.boot_finished = os.path.join(self.instance_link, "boot-finished")
        self.upstart_conf_d = path_cfgs.get('upstart_dir')
        self.seed_dir = os.path.join(self.cloud_dir, 'seed')
        # This one isn't joined, since it should just be read-only
        template_dir = path_cfgs.get('templates_dir', '/etc/cloud/templates/')
        self.template_tpl = os.path.join(template_dir, '%s.tmpl')
        self.lookups = {
            "handlers": "handlers",
            "scripts": "scripts",
            "vendor_scripts": "scripts/vendor",
            "sem": "sem",
            "boothooks": "boothooks",
            "userdata_raw": "user-data.txt",
            "userdata": "user-data.txt.i",
            "obj_pkl": "obj.pkl",
            "cloud_config": "cloud-config.txt",
            "vendor_cloud_config": "vendor-cloud-config.txt",
            "data": "data",
            "vendordata_raw": "vendor-data.txt",
            "vendordata": "vendor-data.txt.i",
            "instance_id": ".instance-id",
            "manual_clean_marker": "manual-clean",
            "warnings": "warnings",
        }
        # Set when a datasource becomes active
        self.datasource = ds

    # get_ipath_cur: get the current instance path for an item
    def get_ipath_cur(self, name=None):
        return self._get_path(self.instance_link, name)

    # get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
    # for a name in dirmap
    def get_cpath(self, name=None):
        return self._get_path(self.cloud_dir, name)

    # _get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    def _get_ipath(self, name=None):
        if not self.datasource:
            return None
        iid = self.datasource.get_instance_id()
        if iid is None:
            return None
        path_safe_iid = str(iid).replace(os.sep, '_')
        ipath = os.path.join(self.cloud_dir, 'instances', path_safe_iid)
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    # returns None + warns if no active datasource....
    def get_ipath(self, name=None):
        ipath = self._get_ipath(name)
        if not ipath:
            LOG.warning(("No per instance data available, "
                         "is there an datasource/iid set?"))
            return None
        else:
            return ipath

    def _get_path(self, base, name=None):
        if name is None:
            return base
        return os.path.join(base, self.lookups[name])

    def get_runpath(self, name=None):
        return self._get_path(self.run_dir, name)


# This config parser will not throw when sections don't exist
# and you are setting values on those sections which is useful
# when writing to new options that may not have corresponding
# sections. Also it can default other values when doing gets
# so that if those sections/options do not exist you will
# get a default instead of an error. Another useful case where
# you can avoid catching exceptions that you typically don't
# care about...

class DefaultingConfigParser(RawConfigParser):
    DEF_INT = 0
    DEF_FLOAT = 0.0
    DEF_BOOLEAN = False
    DEF_BASE = None

    def get(self, section, option):
        value = self.DEF_BASE
        try:
            value = RawConfigParser.get(self, section, option)
        except NoSectionError:
            pass
        except NoOptionError:
            pass
        return value

    def set(self, section, option, value=None):
        if not self.has_section(section) and section.lower() != 'default':
            self.add_section(section)
        RawConfigParser.set(self, section, option, value)

    def remove_option(self, section, option):
        if self.has_option(section, option):
            RawConfigParser.remove_option(self, section, option)

    def getboolean(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_BOOLEAN
        return RawConfigParser.getboolean(self, section, option)

    def getfloat(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_FLOAT
        return RawConfigParser.getfloat(self, section, option)

    def getint(self, section, option):
        if not self.has_option(section, option):
            return self.DEF_INT
        return RawConfigParser.getint(self, section, option)

    def stringify(self, header=None):
        contents = ''
        outputstream = StringIO()
        self.write(outputstream)
        outputstream.flush()
        contents = outputstream.getvalue()
        if header:
            contents = '\n'.join([header, contents, ''])
        return contents


def identity(object):
    return object

# vi: ts=4 expandtab
