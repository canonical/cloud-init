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
import os

from cloudinit.settings import (PER_INSTANCE, PER_ALWAYS, PER_ONCE)

from cloudinit import log as logging
from cloudinit import util

from cloudinit.user_data import boot_hook as bh_part
from cloudinit.user_data import cloud_config as cc_part
from cloudinit.user_data import shell_script as ss_part
from cloudinit.user_data import upstart_job as up_part

LOG = logging.getLogger(__name__)


class DummySemaphores(object):
    def __init__(self):
        pass

    @contextlib.contextmanager
    def lock(self, _name, _freq, _clear_on_fail):
        yield True

    def has_run(self, _name, _freq):
        return False


class Semaphores(object):
    def __init__(self, sem_path):
        self.sem_path = sem_path

    @contextlib.contextmanager
    def lock(self, name, freq, clear_on_fail):
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
            return False
        return True

    def _acquire(self, name, freq):
        if self.has_run(name, freq):
            return None
        # This is a race condition since nothing atomic is happening
        # here, but this should be ok due to the nature of when
        # and where cloud-init runs... (file writing is not a lock..)
        sem_file = self._get_path(name, freq)
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
            sem_path = self.paths.get_ipath("sem")
        elif freq == PER_ONCE:
            sem_path = self.paths.get_cpath("sem")
        if not sem_path:
            return None
        if sem_path not in self.sems:
            self.sems[sem_path] = Semaphores(sem_path)
        return self.sems[sem_path]

    def run(self, name, functor, args, freq=None, clear_on_fail=False):
        sem = self._get_sem(freq)
        if not sem:
            sem = DummySemaphores()
        if not args:
            args = []
        if sem.has_run(name, freq):
            LOG.info("%s already ran (freq=%s)", name, freq)
            return None
        with sem.lock(name, freq, clear_on_fail) as lk:
            if not lk:
                raise RuntimeError("Failed to acquire lock on %s" % name)
            else:
                LOG.debug("Running %s with args %s using lock %s",
                          functor, args, lk)
                return functor(*args)


class ContentHandlers(object):

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
            self.registered[t] = mod
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

        cc_path = self.paths.get_ipath("cloud_config")
        if cc_path:
            cc_h = cc_part.CloudConfigPartHandler(cc_path)
            def_handlers.append(cc_h)

        sc_path = self.paths.get_ipath_cur('scripts')
        if sc_path:
            ss_h = ss_part.ShellScriptPartHandler(sc_path)
            def_handlers.append(ss_h)

        bh_path = self.paths.get_ipath("boothooks")
        if bh_path:
            bh_h = bh_part.BootHookPartHandler(bh_path)
            def_handlers.append(bh_h)

        upstart_pth = self.paths.upstart_conf_d
        if upstart_pth:
            up_h = up_part.UpstartJobPartHandler(upstart_pth)
            def_handlers.append(up_h)

        return def_handlers

    def register_defaults(self):
        registered = set()
        for mod in self._get_default_handlers():
            for t in mod.list_types():
                if not self.is_registered(t):
                    self.registered[t] = mod
                    registered.add(t)
        return registered


class Paths(object):
    def __init__(self, sys_info):
        self.cloud_dir = sys_info.get('cloud_dir', '/var/lib/cloud')
        self.instance_link = os.path.join(self.cloud_dir, 'instance')
        self.boot_finished = os.path.join(self.instance_link, "boot-finished")
        self.upstart_conf_d = sys_info.get('upstart_dir')
        template_dir = sys_info.get('templates_dir', '/etc/cloud/templates/')
        self.template_tpl = os.path.join(template_dir, '%s.tmpl')
        self.seed_dir = os.path.join(self.cloud_dir, 'seed')
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
        self.datasource = None

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

    def _get_ipath(self, name=None):
        if not self.datasource:
            return None
        iid = self.datasource.get_instance_id()
        if iid is None:
            return None
        ipath = os.path.join(self.cloud_dir, 'instances', iid)
        add_on = self.lookups.get(name)
        if add_on:
            ipath = os.path.join(ipath, add_on)
        return ipath

    # (/var/lib/cloud/instances/<instance>/<name>)
    def get_ipath(self, name=None):
        ipath = self._get_ipath(name)
        if not ipath:
            LOG.warn(("No per instance data available, "
                      "is there an datasource/iid set?"))
            return None
        else:
            return ipath
