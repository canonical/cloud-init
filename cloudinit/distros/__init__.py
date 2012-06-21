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

from StringIO import StringIO

import abc
import copy

from cloudinit import importer
from cloudinit import log as logging
from cloudinit import util

# TODO: Make this via config??
IFACE_ACTIONS = {
    'up': ['ifup', '--all'],
    'down': ['ifdown', '--all'],
}

LOG = logging.getLogger(__name__)


class Distro(object):

    __metaclass__ = abc.ABCMeta

    def __init__(self, name, cfg, paths):
        self._paths = paths
        self._cfg = cfg
        self.name = name

    @abc.abstractmethod
    def install_packages(self, pkglist):
        raise NotImplementedError()

    @abc.abstractmethod
    def _write_network(self, settings):
        # In the future use the http://fedorahosted.org/netcf/
        # to write this blob out in a distro format
        raise NotImplementedError()

    def get_option(self, opt_name, default=None):
        return self._cfg.get(opt_name, default)

    @abc.abstractmethod
    def set_hostname(self, hostname):
        raise NotImplementedError()

    @abc.abstractmethod
    def update_hostname(self, hostname, prev_hostname_fn):
        raise NotImplementedError()

    @abc.abstractmethod
    def package_command(self, cmd, args=None):
        raise NotImplementedError()

    def get_package_mirror(self):
        return self.get_option('package_mirror')

    def apply_network(self, settings, bring_up=True):
        # Write it out
        self._write_network(settings)
        # Now try to bring them up
        if bring_up:
            return self._interface_action('up')
        return False

    @abc.abstractmethod
    def set_timezone(self, tz):
        raise NotImplementedError()

    def _get_localhost_ip(self):
        return "127.0.0.1"

    def update_etc_hosts(self, hostname, fqdn):
        # Format defined at
        # http://unixhelp.ed.ac.uk/CGI/man-cgi?hosts
        header = "# Added by cloud-init"
        real_header = "%s on %s" % (header, util.time_rfc2822())
        local_ip = self._get_localhost_ip()
        hosts_line = "%s\t%s %s" % (local_ip, fqdn, hostname)
        new_etchosts = StringIO()
        need_write = False
        need_change = True
        hosts_ro_fn = self._paths.join(True, "/etc/hosts")
        for line in util.load_file(hosts_ro_fn).splitlines():
            if line.strip().startswith(header):
                continue
            if not line.strip() or line.strip().startswith("#"):
                new_etchosts.write("%s\n" % (line))
                continue
            split_line = [s.strip() for s in line.split()]
            if len(split_line) < 2:
                new_etchosts.write("%s\n" % (line))
                continue
            (ip, hosts) = split_line[0], split_line[1:]
            if ip == local_ip:
                if sorted([hostname, fqdn]) == sorted(hosts):
                    need_change = False
                if need_change:
                    line = "%s\n%s" % (real_header, hosts_line)
                    need_change = False
                    need_write = True
            new_etchosts.write("%s\n" % (line))
        if need_change:
            new_etchosts.write("%s\n%s\n" % (real_header, hosts_line))
            need_write = True
        if need_write:
            contents = new_etchosts.getvalue()
            util.write_file(self._paths.join(False, "/etc/hosts"),
                            contents, mode=0644)

    def _interface_action(self, action):
        if action not in IFACE_ACTIONS:
            raise NotImplementedError("Unknown interface action %s" % (action))
        cmd = IFACE_ACTIONS[action]
        try:
            LOG.info("Attempting to run %s interface action using command %s",
                     action, cmd)
            (_out, err) = util.subp(cmd)
            if len(err):
                LOG.warn("Running %s resulted in stderr output: %s", cmd, err)
            return True
        except util.ProcessExecutionError:
            util.logexc(LOG, "Running %s failed", cmd)
            return False


def fetch(distro_name, mods=(__name__, )):
    mod = None
    for m in mods:
        mod_name = "%s.%s" % (m, distro_name)
        try:
            mod = importer.import_module(mod_name)
        except ImportError:
            pass
    if not mod:
        raise RuntimeError("No distribution found for distro %s"
                           % (distro_name))
    distro_cls = getattr(mod, 'Distro')
    return distro_cls
