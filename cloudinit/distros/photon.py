#!/usr/bin/env python3
# vi: ts=4 expandtab
#
# Copyright (C) 2021 VMware Inc.
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import util
from cloudinit import subp
from cloudinit import distros
from cloudinit import helpers
from cloudinit import log as logging
from cloudinit.settings import PER_INSTANCE
from cloudinit.distros import rhel_util as rhutil
from cloudinit.distros.parsers.hostname import HostnameConf

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    hostname_conf_fn = '/etc/hostname'
    network_conf_dir = '/etc/systemd/network/'
    systemd_locale_conf_fn = '/etc/locale.conf'
    resolve_conf_fn = '/etc/systemd/resolved.conf'

    renderer_configs = {
        'networkd': {
            'resolv_conf_fn': resolve_conf_fn,
            'network_conf_dir': network_conf_dir,
        }
    }

    # Should be fqdn if we can use it
    prefer_fqdn = True

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'photon'
        self.init_cmd = ['systemctl']

    def exec_cmd(self, cmd, capture=False):
        LOG.debug('Attempting to run: %s', cmd)
        try:
            (out, err) = subp.subp(cmd, capture=capture)
            if err:
                LOG.warning('Running %s resulted in stderr output: %s',
                            cmd, err)
            return True, out, err
        except subp.ProcessExecutionError:
            util.logexc(LOG, 'Command %s failed', cmd)
            return False, None, None

    def apply_locale(self, locale, out_fn=None):
        # This has a dependancy on glibc-i18n, user need to manually install it
        # and enable the option in cloud.cfg
        if not out_fn:
            out_fn = self.systemd_locale_conf_fn

        locale_cfg = {
            'LANG': locale,
        }

        rhutil.update_sysconfig_file(out_fn, locale_cfg)

        # rhutil will modify /etc/locale.conf
        # For locale change to take effect, reboot is needed or we can restart
        # systemd-localed. This is equivalent of localectl
        cmd = ['systemctl', 'restart', 'systemd-localed']
        _ret, _out, _err = self.exec_cmd(cmd)

    def install_packages(self, pkglist):
        # self.update_package_sources()
        self.package_command('install', pkgs=pkglist)

    def _bring_up_interfaces(self, device_names):
        cmd = ['systemctl', 'restart', 'systemd-networkd', 'systemd-resolved']
        LOG.debug('Attempting to run bring up interfaces using command %s',
                  cmd)
        ret, _out, _err = self.exec_cmd(cmd)
        return ret

    def _write_hostname(self, hostname, out_fn):
        conf = None
        try:
            # Try to update the previous one
            # Let's see if we can read it first.
            conf = HostnameConf(util.load_file(out_fn))
            conf.parse()
        except IOError:
            pass
        if not conf:
            conf = HostnameConf('')
        conf.set_hostname(hostname)
        util.write_file(out_fn, str(conf), mode=0o644)

    def _read_system_hostname(self):
        sys_hostname = self._read_hostname(self.hostname_conf_fn)
        return (self.hostname_conf_fn, sys_hostname)

    def _read_hostname(self, filename, default=None):
        _ret, out, _err = self.exec_cmd(['hostname'])

        return out if out else default

    def _get_localhost_ip(self):
        return '127.0.1.1'

    def set_timezone(self, tz):
        distros.set_etc_timezone(tz=tz, tz_file=self._find_tz_file(tz))

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['tdnf', '-y']
        if args and isinstance(args, str):
            cmd.append(args)
        elif args and isinstance(args, list):
            cmd.extend(args)

        cmd.append(command)

        pkglist = util.expand_package_list('%s-%s', pkgs)
        cmd.extend(pkglist)

        # Allow the output of this to flow outwards (ie not be captured)
        _ret, _out, _err = self.exec_cmd(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run('update-sources', self.package_command,
                         ['makecache'], freq=PER_INSTANCE)
