# Copyright (C) 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import distros

from cloudinit.distros.parsers.hostname import HostnameConf

from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.distros import net_util
from cloudinit.distros import rhel_util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(distros.Distro):
    clock_conf_fn = '/etc/sysconfig/clock'
    locale_conf_fn = '/etc/sysconfig/language'
    network_conf_fn = '/etc/sysconfig/network'
    hostname_conf_fn = '/etc/HOSTNAME'
    network_script_tpl = '/etc/sysconfig/network/ifcfg-%s'
    resolve_conf_fn = '/etc/resolv.conf'
    tz_local_fn = '/etc/localtime'

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'suse'

    def install_packages(self, pkglist):
        self.package_command('install', args='-l', pkgs=pkglist)

    def _write_network(self, settings):
        # Convert debian settings to ifcfg format
        entries = net_util.translate_network(settings)
        LOG.debug("Translated ubuntu style network settings %s into %s",
                  settings, entries)
        # Make the intermediate format as the suse format...
        nameservers = []
        searchservers = []
        dev_names = entries.keys()
        for (dev, info) in entries.items():
            net_fn = self.network_script_tpl % (dev)
            mode = info.get('auto')
            if mode and mode.lower() == 'true':
                mode = 'auto'
            else:
                mode = 'manual'
            net_cfg = {
                'BOOTPROTO': info.get('bootproto'),
                'BROADCAST': info.get('broadcast'),
                'GATEWAY': info.get('gateway'),
                'IPADDR': info.get('address'),
                'LLADDR': info.get('hwaddress'),
                'NETMASK': info.get('netmask'),
                'STARTMODE': mode,
                'USERCONTROL': 'no'
            }
            if dev != 'lo':
                net_cfg['ETHERDEVICE'] = dev
                net_cfg['ETHTOOL_OPTIONS'] = ''
            else:
                net_cfg['FIREWALL'] = 'no'
            rhel_util.update_sysconfig_file(net_fn, net_cfg, True)
            if 'dns-nameservers' in info:
                nameservers.extend(info['dns-nameservers'])
            if 'dns-search' in info:
                searchservers.extend(info['dns-search'])
        if nameservers or searchservers:
            rhel_util.update_resolve_conf_file(self.resolve_conf_fn,
                                               nameservers, searchservers)
        return dev_names

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = self.locale_conf_fn
        locale_cfg = {
            'RC_LANG': locale,
        }
        rhel_util.update_sysconfig_file(out_fn, locale_cfg)

    def _write_hostname(self, hostname, out_fn):
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

    def _read_system_hostname(self):
        host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

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

    def _bring_up_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate '
                                'the device name "all"') % (self.name))
        return distros.Distro._bring_up_interfaces(self, device_names)

    def set_timezone(self, tz):
        tz_file = self._find_tz_file(tz)
        # Adjust the sysconfig clock zone setting
        clock_cfg = {
            'TIMEZONE': str(tz),
        }
        rhel_util.update_sysconfig_file(self.clock_conf_fn, clock_cfg)
        # This ensures that the correct tz will be used for the system
        util.copy(tz_file, self.tz_local_fn)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['zypper']
        # No user interaction possible, enable non-interactive mode
        cmd.append('--non-interactive')

        # Comand is the operation, such as install
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

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ['refresh'], freq=PER_INSTANCE)

# vi: ts=4 expandtab
