# vi: ts=4 expandtab
#
#    Copyright (C) 2014 Rackspace, US Inc.
#
#    Author: Nate House <nathan.house@rackspace.com>
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
from cloudinit import util

from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    locale_conf_fn = "/etc/locale.gen"
    network_conf_fn = "/etc/conf.d/net"
    init_cmd = ['']  # init scripts

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'gentoo'
        # Fix sshd restarts
        cfg['ssh_svcname'] = '/etc/init.d/sshd'

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self.locale_conf_fn
        util.subp(['locale-gen', '-G', locale], capture=False)
        # "" provides trailing newline during join
        lines = [
            util.make_header(),
            'LANG="%s"' % (locale),
            "",
        ]
        util.write_file(out_fn, "\n".join(lines))

    def install_packages(self, pkglist):
        self.update_package_sources()
        self.package_command('', pkgs=pkglist)

    def _write_network(self, settings):
        util.write_file(self.network_conf_fn, settings)
        return ['all']

    def _bring_up_interface(self, device_name):
        cmd = ['/etc/init.d/net.%s' % device_name, 'restart']
        LOG.debug("Attempting to run bring up interface %s using command %s",
                   device_name, cmd)
        try:
            (_out, err) = util.subp(cmd)
            if len(err):
                LOG.warn("Running %s resulted in stderr output: %s", cmd, err)
            return True
        except util.ProcessExecutionError:
            util.logexc(LOG, "Running interface command %s failed", cmd)
            return False

    def _bring_up_interfaces(self, device_names):
        use_all = False
        for d in device_names:
            if d == 'all':
                use_all = True
        if use_all:
            # Grab device names from init scripts
            cmd = ['ls', '/etc/init.d/net.*']
            try:
                (_out, err) = util.subp(cmd)
                if len(err):
                    LOG.warn("Running %s resulted in stderr output: %s", cmd,
                            err)
            except util.ProcessExecutionError:
                util.logexc(LOG, "Running interface command %s failed", cmd)
                return False
            devices = [x.split('.')[2] for x in _out.split('  ')]
            return distros.Distro._bring_up_interfaces(self, devices)
        else:
            return distros.Distro._bring_up_interfaces(self, device_names)

    def _select_hostname(self, hostname, fqdn):
        # Prefer the short hostname over the long
        # fully qualified domain name
        if not hostname:
            return fqdn
        return hostname

    def _write_hostname(self, your_hostname, out_fn):
        conf = None
        try:
            # Try to update the previous one
            # so lets see if we can read it first.
            conf = self._read_hostname_conf(out_fn)
        except IOError:
            pass
        if not conf:
            conf = HostnameConf('')
        conf.set_hostname(your_hostname)
        util.write_file(out_fn, str(conf), 0644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_file(filename))
        conf.parse()
        return conf

    def _read_hostname(self, filename, default=None):
        hostname = None
        try:
            conf = self._read_hostname_conf(filename)
            hostname = conf.hostname
        except IOError:
            pass
        if not hostname:
            return default
        return hostname

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['emerge']
        # Redirect output
        cmd.append("--quiet")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        if command:
            cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["-u", "world"], freq=PER_INSTANCE)
