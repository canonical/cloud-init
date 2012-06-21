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

import contextlib
import io
import os

from ConfigParser import (NoSectionError, NoOptionError, RawConfigParser)

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS, PER_ONCE)

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


class LockFailure(Exception):
    pass


class DummySemaphores(object):
    def __init__(self):
        pass

    @contextlib.contextmanager
    def lock(self, _name, _freq, _clear_on_fail=False):
        yield True

    def has_run(self, _name, _freq):
        return False

    def clear(self, _name, _freq):
        return True

    def clear_all(self):
        pass


class FileSemaphores(object):
    def __init__(self, sem_path):
        self.sem_path = sem_path

    @contextlib.contextmanager
    def lock(self, name, freq, clear_on_fail=False):
        try:
            yield self._acquire(name, freq)
        except:
            if clear_on_fail:
                self.clear(name, freq)
            raise

    def clear(self, name, freq):
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
        return sem_file

    def has_run(self, name, freq):
        if not freq or freq == PER_ALWAYS:
            return False
        sem_file = self._get_path(name, freq)
        # This isn't really a good atomic check
        # but it suffices for where and when cloudinit runs
        if os.path.exists(sem_file):
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
            LOG.info("%s already ran (freq=%s)", name, freq)
            return (False, None)
        with sem.lock(name, freq, clear_on_fail) as lk:
            if not lk:
                raise LockFailure("Failed to acquire lock for %s" % name)
            else:
                LOG.debug("Running %s with args %s using lock %s (%s)",
                          functor, args, util.obj_name(lk), lk)
                if isinstance(args, (dict)):
                    results = functor(**args)
                else:
                    results = functor(*args)
                return (True, results)


class ContentHandlers(object):

    def __init__(self):
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
            self.registered[t] = mod
            types.add(t)
        return types

    def _get_handler(self, content_type):
        return self.registered[content_type]

    def items(self):
        return self.registered.items()

    def iteritems(self):
        return self.registered.iteritems()

    def register_defaults(self, defs):
        registered = set()
        for mod in defs:
            for t in mod.list_types():
                if not self.is_registered(t):
                    self.registered[t] = mod
                    registered.add(t)
        return registered


class Paths(object):
    def __init__(self, path_cfgs, ds=None):
        self.cfgs = path_cfgs
        # Populate all the initial paths
        self.cloud_dir = self.join(False,
                                   path_cfgs.get('cloud_dir',
                                                 '/var/lib/cloud'))
        self.instance_link = os.path.join(self.cloud_dir, 'instance')
        self.boot_finished = os.path.join(self.instance_link, "boot-finished")
        self.upstart_conf_d = path_cfgs.get('upstart_dir')
        if self.upstart_conf_d:
            self.upstart_conf_d = self.join(False, self.upstart_conf_d)
        self.seed_dir = os.path.join(self.cloud_dir, 'seed')
        # This one isn't joined, since it should just be read-only
        template_dir = path_cfgs.get('templates_dir', '/etc/cloud/templates/')
        self.template_tpl = os.path.join(template_dir, '%s.tmpl')
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
        # Set when a datasource becomes active
        self.datasource = ds

    # joins the paths but also appends a read
    # or write root if available
    def join(self, read_only, *paths):
        if read_only:
            root = self.cfgs.get('read_root')
        else:
            root = self.cfgs.get('write_root')
        if not paths:
            return root
        if len(paths) > 1:
            joined = os.path.join(*paths)
        else:
            joined = paths[0]
        if root:
            pre_joined = joined
            # Need to remove any starting '/' since this
            # will confuse os.path.join
            joined = joined.lstrip("/")
            joined = os.path.join(root, joined)
            LOG.debug("Translated %s to adjusted path %s (read-only=%s)",
                      pre_joined, joined, read_only)
        return joined

    # get_ipath_cur: get the current instance path for an item
    def get_ipath_cur(self, name=None):
        ipath = self.instance_link
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # get_cpath : get the "clouddir" (/var/lib/cloud/<name>)
    # for a name in dirmap
    def get_cpath(self, name=None):
        cpath = self.cloud_dir
        add_on = self.lookups.get(name)
        if add_on:
            cpath = os.path.join(cpath, add_on)
        return cpath

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    def _get_ipath(self, name=None):
        if not self.datasource:
            return None
        iid = self.datasource.get_instance_id()
        if iid is None:
            return None
        ipath = os.path.join(self.cloud_dir, 'instances', str(iid))
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # get_ipath : get the instance path for a name in pathmap
    # (/var/lib/cloud/instances/<instance>/<name>)
    def get_ipath(self, name=None):
        ipath = self._get_ipath(name)
        if not ipath:
            LOG.warn(("No per instance data available, "
                      "is there an datasource/iid set?"))
            return None
        else:
            return ipath


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

    def set(self, section, option, value):
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
        with io.BytesIO() as outputstream:
            self.write(outputstream)
            outputstream.flush()
            contents = outputstream.getvalue()
            if header:
                contents = "\n".join([header, contents])
        return contents
