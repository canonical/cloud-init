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

import os

from cloudinit import distros
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import (PER_INSTANCE)


LOG = logging.getLogger(__name__)


class Distro(distros.Distro):

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.apt_get('install', pkglist)

    def apply_network(self, settings):
        pass

    # apt_get top level command (install, update...), and args to pass it
    def apt_get(self, tlc, args=None):
        e = os.environ.copy()
        e['DEBIAN_FRONTEND'] = 'noninteractive'
        cmd = ['apt-get', '--option', 'Dpkg::Options::=--force-confold',
               '--assume-yes', tlc]
        if args:
            cmd.extend(args)
        util.subp(cmd, env=e)

    def update_package_sources(self):
        self.cloud.run("update-sources", self.apt_get, ["update"], freq=PER_INSTANCE)