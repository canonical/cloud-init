#    Copyright (C) 2017 SUSE LLC
#    Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
#    Author: Robert Schweikert <rjschwei@suse.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
#    Leaning very heavily on the RHEL and Debian implementation
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros

from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.distros import rhel_util as rhutil
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    clock_conf_fn = '/etc/sysconfig/clock'
    hostname_conf_fn = '/etc/HOSTNAME'
    init_cmd = ['service']
    locale_conf_fn = '/etc/sysconfig/language'
    network_conf_fn = '/etc/sysconfig/network/config'
    network_script_tpl = '/etc/sysconfig/network/ifcfg-%s'
    resolve_conf_fn = '/etc/resolv.conf'
    route_conf_tpl = '/etc/sysconfig/network/ifroute-%s'
    systemd_hostname_conf_fn = '/etc/hostname'
    systemd_locale_conf_fn = '/etc/locale.conf'
    tz_local_fn = '/etc/localtime'
    renderer_configs = {
        'sysconfig': {
            'control': 'etc/sysconfig/network/config',
            'iface_templates': '%(base)s/network/ifcfg-%(name)s',
            'route_templates': {
                'ipv4': '%(base)s/network/ifroute-%(name)s',
                'ipv6': '%(base)s/network/ifroute-%(name)s',
            }
        }
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'suse'
        cfg['ssh_svcname'] = 'sshd'
        if self.uses_systemd():
            self.init_cmd = ['systemctl']
            cfg['ssh_svcname'] = 'sshd.service'

    def apply_locale(self, locale, out_fn=None):
        if self.uses_systemd():
            if not out_fn:
                out_fn = self.systemd_locale_conf_fn
            locale_cfg = {'LANG': locale}
        else:
            if not out_fn:
                out_fn = self.locale_conf_fn
            locale_cfg = {'RC_LANG': locale}
        rhutil.update_sysconfig_file(out_fn, locale_cfg)

    def install_packages(self, pkglist):
        self.package_command(
            'install',
            args='--auto-agree-with-licenses',
            pkgs=pkglist
        )

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        # No user interaction possible, enable non-interactive mode
        cmd = ['zypper', '--non-interactive']

        # Command is the operation, such as install
        if command == 'upgrade':
            command = 'update'
        cmd.append(command)

        # args are the arguments to the command, not global options
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, capture=False)

    def set_timezone(self, tz):
        tz_file = self._find_tz_file(tz)
        if self.uses_systemd():
            # Currently, timedatectl complains if invoked during startup
            # so for compatibility, create the link manually.
            util.del_file(self.tz_local_fn)
            util.sym_link(tz_file, self.tz_local_fn)
        else:
            # Adjust the sysconfig clock zone setting
            clock_cfg = {
                'TIMEZONE': str(tz),
            }
            rhutil.update_sysconfig_file(self.clock_conf_fn, clock_cfg)
            # This ensures that the correct tz will be used for the system
            util.copy(tz_file, self.tz_local_fn)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ['refresh'], freq=PER_INSTANCE)

    def _bring_up_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate '
                                'the device name "all"') % (self.name))
        return distros.Distro._bring_up_interfaces(self, device_names)

    def _read_hostname(self, filename, default=None):
        if self.uses_systemd() and filename.endswith('/previous-hostname'):
            return util.load_file(filename).strip()
        elif self.uses_systemd():
            (out, _err) = util.subp(['hostname'])
            if len(out):
                return out
            else:
                return default
        else:
            try:
                conf = self._read_hostname_conf(filename)
                hostname = conf.hostname
            except IOError:
                pass
            if not hostname:
                return default
            return hostname

    def _read_hostname_conf(self, filename):
        conf = HostnameConf(util.load_file(filename))
        conf.parse()
        return conf

    def _read_system_hostname(self):
        if self.uses_systemd():
            host_fn = self.systemd_hostname_conf_fn
        else:
            host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

    def _write_hostname(self, hostname, out_fn):
        if self.uses_systemd() and out_fn.endswith('/previous-hostname'):
            util.write_file(out_fn, hostname)
        elif self.uses_systemd():
            util.subp(['hostnamectl', 'set-hostname', str(hostname)])
        else:
            conf = None
            try:
                # Try to update the previous one
                # so lets see if we can read it first.
                conf = self._read_hostname_conf(out_fn)
            except IOError:
                pass
            if not conf:
                conf = HostnameConf('')
            conf.set_hostname(hostname)
            util.write_file(out_fn, str(conf), 0o644)

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    @property
    def preferred_ntp_clients(self):
        """The preferred ntp client is dependent on the version."""

        """Allow distro to determine the preferred ntp client list"""
        if not self._preferred_ntp_clients:
            distro_info = util.system_info()['dist']
            name = distro_info[0]
            major_ver = int(distro_info[1].split('.')[0])

            # This is horribly complicated because of a case of
            # "we do not care if versions should be increasing syndrome"
            if (
                (major_ver >= 15 and 'openSUSE' not in name) or
                (major_ver >= 15 and 'openSUSE' in name and major_ver != 42)
            ):
                self._preferred_ntp_clients = ['chrony',
                                               'systemd-timesyncd', 'ntp']
            else:
                self._preferred_ntp_clients = ['ntp',
                                               'systemd-timesyncd', 'chrony']

        return self._preferred_ntp_clients

# vi: ts=4 expandtab
