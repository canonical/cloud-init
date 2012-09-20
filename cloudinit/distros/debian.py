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

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self._paths.join(False, '/etc/default/locale')
        util.subp(['locale-gen', locale], capture=False)
        util.subp(['update-locale', locale], capture=False)
        lines = ["# Created by cloud-init", 'LANG="%s"' % (locale), ""]
        util.write_file(out_fn, "\n".join(lines))

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('install', pkglist)

    def _write_network(self, settings):
        net_fn = self._paths.join(False, "/etc/network/interfaces")
        util.write_file(net_fn, settings)
        return ['all']

    def _bring_up_interfaces(self, device_names):
        use_all = False
        for d in device_names:
            if d == 'all':
                use_all = True
        if use_all:
            return distros.Distro._bring_up_interface(self, '--all')
        else:
            return distros.Distro._bring_up_interfaces(self, device_names)

    def set_hostname(self, hostname):
        out_fn = self._paths.join(False, "/etc/hostname")
        self._write_hostname(hostname, out_fn)
        if out_fn == '/etc/hostname':
            # Only do this if we are running in non-adjusted root mode
            LOG.debug("Setting hostname to %s", hostname)
            util.subp(['hostname', hostname])

    def _write_hostname(self, hostname, out_fn):
        # "" gives trailing newline.
        util.write_file(out_fn, "%s\n" % str(hostname), 0644)

    def update_hostname(self, hostname, prev_fn):
        hostname_prev = self._read_hostname(prev_fn)
        read_fn = self._paths.join(True, "/etc/hostname")
        hostname_in_etc = self._read_hostname(read_fn)
        update_files = []
        if not hostname_prev or hostname_prev != hostname:
            update_files.append(prev_fn)
        if (not hostname_in_etc or
            (hostname_in_etc == hostname_prev and
             hostname_in_etc != hostname)):
            write_fn = self._paths.join(False, "/etc/hostname")
            update_files.append(write_fn)
        for fn in update_files:
            try:
                self._write_hostname(hostname, fn)
            except:
                util.logexc(LOG, "Failed to write hostname %s to %s",
                            hostname, fn)
        if (hostname_in_etc and hostname_prev and
            hostname_in_etc != hostname_prev):
            LOG.debug(("%s differs from /etc/hostname."
                        " Assuming user maintained hostname."), prev_fn)
        if "/etc/hostname" in update_files:
            # Only do this if we are running in non-adjusted root mode
            LOG.debug("Setting hostname to %s", hostname)
            util.subp(['hostname', hostname])

    def _read_hostname(self, filename, default=None):
        contents = util.load_file(filename, quiet=True)
        for line in contents.splitlines():
            c_pos = line.find("#")
            # Handle inline comments
            if c_pos != -1:
                line = line[0:c_pos]
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
            raise RuntimeError(("Invalid timezone %s,"
                                " no file found at %s") % (tz, tz_file))
        # "" provides trailing newline during join
        tz_lines = ["# Created by cloud-init", str(tz), ""]
        tz_fn = self._paths.join(False, "/etc/timezone")
        util.write_file(tz_fn, "\n".join(tz_lines))
        util.copy(tz_file, self._paths.join(False, "/etc/localtime"))

    def package_command(self, command, args=None):
        e = os.environ.copy()
        # See: http://tiny.cc/kg91fw
        # Or: http://tiny.cc/mh91fw
        e['DEBIAN_FRONTEND'] = 'noninteractive'
        cmd = ['apt-get', '--option', 'Dpkg::Options::=--force-confold',
               '--assume-yes', '--quiet', command]
        if args:
            cmd.extend(args)
        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, env=e, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["update"], freq=PER_INSTANCE)

    def get_primary_arch(self):
        (arch, _err) = util.subp(['dpkg', '--print-architecture'])
        return str(arch).strip()
