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

from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging

LOG = logging.getLogger(__name__)


class Cloud(object):
    def __init__(self, datasource, paths, cfg):
        self.datasource = datasource
        self.paths = paths
        self.cfg = cfg
        self.distro = distros.fetch(cfg, self)
        self.runners = helpers.Runners(paths)

    def run(self, name, functor, args, freq=None, clear_on_fail=False):
        return self.runners.run(name, functor, args, freq, clear_on_fail)

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
