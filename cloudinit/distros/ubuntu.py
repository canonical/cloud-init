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
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain 
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
    
    def install_packages(self, pkglist):
        self._update_package_sources()
        self.package_command('install', pkglist)

    def _write_network(self, settings):
        util.write_file("/etc/network/interfaces", settings)

    def set_hostname(self, hostname):
        self._write_hostname(hostname, "/etc/hostname")
        LOG.debug("Setting hostname to %s", hostname)
        util.subp(['hostname', hostname])

    def _write_hostname(self, hostname, out_fn):
        contents = "%s\n" % (hostname)
        util.write_file(out_fn, contents, 0644)

    def update_hostname(self, hostname, prev_file):
        hostname_prev = self._read_hostname(prev_file)
        hostname_in_etc = self._read_hostname("/etc/hostname")
        update_files = []
        if not hostname_prev or hostname_prev != hostname:
            update_files.append(prev_file)
        if (not hostname_in_etc or
           (hostname_in_etc == hostname_prev and hostname_in_etc != hostname)):
            update_files.append("/etc/hostname")
        for fn in update_files:
            try:
                self._write_hostname(hostname, fn)
            except:
                util.logexc(LOG, "Failed to write hostname %s to %s",
                            hostname, fn)
        if (hostname_in_etc and hostname_prev and
            hostname_in_etc != hostname_prev):
            LOG.debug(("%s differs from /etc/hostname."
                        " Assuming user maintained hostname."), prev_file)
        if "/etc/hostname" in update_files:
            LOG.debug("Setting hostname to %s", hostname)
            util.subp(['hostname', hostname])

    def _read_hostname(self, filename, default=None):
        contents = util.load_file(filename, quiet=True)
        for line in contents.splitlines():
            hpos = line.find("#")
            # Handle inline comments
            if hpos != -1:
                line = line[0:hpos]
            line_c = line.strip()
            if line_c:
                return line_c
        return default

    def _get_localhost_ip(self):
        # Note: http://www.leonardoborda.com/blog/127-0-1-1-ubuntu-debian/
        return "127.0.1.1"

    def set_timezone(self, tz):
        tz_file = os.path.join("/usr/share/zoneinfo", tz)
        if not os.path.isfile(tz_file):
            raise Exception(("Invalid timezone %s,"
                             " no file found at %s") % (tz, tz_file))
        tz_contents = "%s\n" % tz
        util.write_file("/etc/timezone", tz_contents)
        util.copy(tz_file, "/etc/localtime")

    def package_command(self, command, args=None):
        e = os.environ.copy()
        # See: http://tiny.cc/kg91fw
        # Or: http://tiny.cc/mh91fw
        e['DEBIAN_FRONTEND'] = 'noninteractive'
        cmd = ['apt-get', '--option', 'Dpkg::Options::=--force-confold',
               '--assume-yes', command]
        if args:
            cmd.extend(args)
        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, env=e, capture=False)

    def _update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["update"], freq=PER_INSTANCE)