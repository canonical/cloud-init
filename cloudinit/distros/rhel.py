# Copyright (C) 2012 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
# Copyright (C) 2012 Yahoo! Inc.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Joshua Harlow <harlowja@yahoo-inc.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.distros import rhel_util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


def _make_sysconfig_bool(val):
    if val:
        return 'yes'
    else:
        return 'no'


class Distro(distros.Distro):
    # See: https://access.redhat.com/documentation/en-US/Red_Hat_Enterprise_Linux/7/html/Networking_Guide/sec-Network_Configuration_Using_sysconfig_Files.html # noqa
    clock_conf_fn = "/etc/sysconfig/clock"
    locale_conf_fn = '/etc/sysconfig/i18n'
    systemd_locale_conf_fn = '/etc/locale.conf'
    network_conf_fn = "/etc/sysconfig/network"
    hostname_conf_fn = "/etc/sysconfig/network"
    systemd_hostname_conf_fn = "/etc/hostname"
    network_script_tpl = '/etc/sysconfig/network-scripts/ifcfg-%s'
    resolve_conf_fn = "/etc/resolv.conf"
    tz_local_fn = "/etc/localtime"
    usr_lib_exec = "/usr/libexec"
    renderer_configs = {
        'sysconfig': {
            'control': 'etc/sysconfig/network',
            'iface_templates': '%(base)s/network-scripts/ifcfg-%(name)s',
            'route_templates': {
                'ipv4': '%(base)s/network-scripts/route-%(name)s',
                'ipv6': '%(base)s/network-scripts/route6-%(name)s'
            }
        }
    }

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'redhat'
        cfg['ssh_svcname'] = 'sshd'

    def install_packages(self, pkglist):
        self.package_command('install', pkgs=pkglist)

    def _write_network_config(self, netconfig):
        return self._supported_write_network_config(netconfig)

    def apply_locale(self, locale, out_fn=None):
        if self.uses_systemd():
            if not out_fn:
                out_fn = self.systemd_locale_conf_fn
            out_fn = self.systemd_locale_conf_fn
        else:
            if not out_fn:
                out_fn = self.locale_conf_fn
        locale_cfg = {
            'LANG': locale,
        }
        rhel_util.update_sysconfig_file(out_fn, locale_cfg)

    def _write_hostname(self, hostname, out_fn):
        # systemd will never update previous-hostname for us, so
        # we need to do it ourselves
        if self.uses_systemd() and out_fn.endswith('/previous-hostname'):
            util.write_file(out_fn, hostname)
        elif self.uses_systemd():
            util.subp(['hostnamectl', 'set-hostname', str(hostname)])
        else:
            host_cfg = {
                'HOSTNAME': hostname,
            }
            rhel_util.update_sysconfig_file(out_fn, host_cfg)

    def _select_hostname(self, hostname, fqdn):
        # Should be fqdn if we can use it
        # See: https://www.centos.org/docs/5/html/Deployment_Guide-en-US/ch-sysconfig.html#s2-sysconfig-network # noqa
        if fqdn:
            return fqdn
        return hostname

    def _read_system_hostname(self):
        if self.uses_systemd():
            host_fn = self.systemd_hostname_conf_fn
        else:
            host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

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
            (_exists, contents) = rhel_util.read_sysconfig_file(filename)
            if 'HOSTNAME' in contents:
                return contents['HOSTNAME']
            else:
                return default

    def _bring_up_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate '
                                'the device name "all"') % (self.name))
        return distros.Distro._bring_up_interfaces(self, device_names)

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
                'ZONE': str(tz),
            }
            rhel_util.update_sysconfig_file(self.clock_conf_fn, clock_cfg)
            # This ensures that the correct tz will be used for the system
            util.copy(tz_file, self.tz_local_fn)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        if util.which('dnf'):
            LOG.debug('Using DNF for package management')
            cmd = ['dnf']
        else:
            LOG.debug('Using YUM for package management')
            # the '-t' argument makes yum tolerant of errors on the command
            # line with regard to packages.
            #
            # For example: if you request to install foo, bar and baz and baz
            # is installed; yum won't error out complaining that baz is already
            # installed.
            cmd = ['yum', '-t']
        # Determines whether or not yum prompts for confirmation
        # of critical actions. We don't want to prompt...
        cmd.append("-y")

        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["makecache"], freq=PER_INSTANCE)

# vi: ts=4 expandtab
