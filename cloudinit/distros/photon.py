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
from cloudinit.distros import net_util
from cloudinit.settings import PER_INSTANCE
from cloudinit.distros import rhel_util as rhutil
from cloudinit.net.network_state import mask_to_net_prefix
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

    def _write_network_config(self, netconfig):
        if isinstance(netconfig, str):
            self._write_network_(netconfig)
            return
        return self._supported_write_network_config(netconfig)

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

    def _generate_resolv_conf(self):
        resolv_conf_fn = self.resolve_conf_fn
        resolv_templ_fn = 'systemd.resolved.conf'

        return resolv_conf_fn, resolv_templ_fn

    def _write_network_(self, settings):
        entries = net_util.translate_network(settings)
        LOG.debug('Translated ubuntu style network settings %s into %s',
                  settings, entries)
        route_entries = []
        route_entries = translate_routes(settings)
        dev_names = entries.keys()
        nameservers = []
        searchdomains = []
        # Format for systemd
        for (dev, info) in entries.items():
            if 'dns-nameservers' in info:
                nameservers.extend(info['dns-nameservers'])
            if 'dns-search' in info:
                searchdomains.extend(info['dns-search'])
            if dev == 'lo':
                continue

            net_fn = self.network_conf_dir + '10-cloud-init-' + dev
            net_fn += '.network'
            dhcp_enabled = 'no'
            if info.get('bootproto') == 'dhcp':
                if (settings.find('inet dhcp') >= 0 and
                        settings.find('inet6 dhcp') >= 0):
                    dhcp_enabled = 'yes'
                else:
                    if info.get('inet6') is True:
                        dhcp_enabled = 'ipv6'
                    else:
                        dhcp_enabled = 'ipv4'

            net_cfg = {
                'Name': dev,
                'DHCP': dhcp_enabled,
            }

            if info.get('hwaddress'):
                net_cfg['MACAddress'] = info.get('hwaddress')
            if info.get('address'):
                net_cfg['Address'] = '%s' % (info.get('address'))
                if info.get('netmask'):
                    net_cfg['Address'] += '/%s' % (
                        mask_to_net_prefix(info.get('netmask')))
            if info.get('gateway'):
                net_cfg['Gateway'] = info.get('gateway')
            if info.get('dns-nameservers'):
                net_cfg['DNS'] = str(
                    tuple(info.get('dns-nameservers'))).replace(',', '')
            if info.get('dns-search'):
                net_cfg['Domains'] = str(
                    tuple(info.get('dns-search'))).replace(',', '')
            route_entry = []
            if dev in route_entries:
                route_entry = route_entries[dev]
                route_index = 0
                found = True
                while found:
                    route_name = 'routes.' + str(route_index)
                    if route_name in route_entries[dev]:
                        val = str(tuple(route_entries[dev][route_name]))
                        val = val.replace(',', '')
                        if val:
                            net_cfg[route_name] = val
                    else:
                        found = False
                    route_index += 1

            if info.get('auto'):
                self._write_interface_file(net_fn, net_cfg, route_entry)

        resolve_data = []
        new_resolve_data = []
        with open(self.resolve_conf_fn, 'r') as rf:
            resolve_data = rf.readlines()
        LOG.debug('Old Resolve Data\n')
        LOG.debug('%s', resolve_data)
        for item in resolve_data:
            if ((nameservers and ('DNS=' in item)) or
                    (searchdomains and ('Domains=' in item))):
                continue
            else:
                new_resolve_data.append(item)

        new_resolve_data = new_resolve_data + \
            convert_resolv_conf(nameservers, searchdomains)
        LOG.debug('New resolve data\n')
        LOG.debug('%s', new_resolve_data)
        if nameservers or searchdomains:
            util.write_file(self.resolve_conf_fn, ''.join(new_resolve_data))

        return dev_names

    def _write_interface_file(self, net_fn, net_cfg, route_entry):
        if not net_cfg['Name']:
            return
        content = '[Match]\n'
        content += 'Name=%s\n' % (net_cfg['Name'])
        if 'MACAddress' in net_cfg:
            content += 'MACAddress=%s\n' % (net_cfg['MACAddress'])
        content += '[Network]\n'

        if 'DHCP' in net_cfg and net_cfg['DHCP'] in {'yes', 'ipv4', 'ipv6'}:
            content += 'DHCP=%s\n' % (net_cfg['DHCP'])
        else:
            if 'Address' in net_cfg:
                content += 'Address=%s\n' % (net_cfg['Address'])
            if 'Gateway' in net_cfg:
                content += 'Gateway=%s\n' % (net_cfg['Gateway'])
            if 'DHCP' in net_cfg and net_cfg['DHCP'] == 'no':
                content += 'DHCP=%s\n' % (net_cfg['DHCP'])

            route_index = 0
            found = True
            if route_entry:
                while found:
                    route_name = 'routes.' + str(route_index)
                    if route_name in route_entry:
                        content += '[Route]\n'
                        if len(route_entry[route_name]) != 2:
                            continue
                        content += 'Gateway=%s\n' % (
                            route_entry[route_name][0])
                        content += 'Destination=%s\n' % (
                            route_entry[route_name][1])
                    else:
                        found = False
                    route_index += 1

        util.write_file(net_fn, content)


def convert_resolv_conf(nameservers, searchdomains):
    ''' Returns a string formatted for resolv.conf '''
    result = []
    if nameservers:
        nslist = 'DNS='
        for ns in nameservers:
            nslist = nslist + '%s ' % ns
        nslist = nslist + '\n'
        result.append(str(nslist))
    if searchdomains:
        sdlist = 'Domains='
        for sd in searchdomains:
            sdlist = sdlist + '%s ' % sd
        sdlist = sdlist + '\n'
        result.append(str(sdlist))
    return result


def translate_routes(settings):
    entries = []
    for line in settings.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        split_up = line.split(None, 1)
        if len(split_up) <= 1:
            continue
        entries.append(split_up)
    consume = {}
    ifaces = []
    for (cmd, args) in entries:
        if cmd == 'iface':
            if consume:
                ifaces.append(consume)
                consume = {}
            consume[cmd] = args
        else:
            consume[cmd] = args

    absorb = False
    for (cmd, args) in consume.items():
        if cmd == 'iface':
            absorb = True
    if absorb:
        ifaces.append(consume)
    out_ifaces = {}
    for info in ifaces:
        if 'iface' not in info:
            continue
        iface_details = info['iface'].split(None)
        dev_name = None
        if len(iface_details) >= 1:
            dev = iface_details[0].strip().lower()
            if dev:
                dev_name = dev
        if not dev_name:
            continue
        route_info = {}
        route_index = 0
        found = True
        while found:
            route_name = 'routes.' + str(route_index)
            if route_name in info:
                val = info[route_name].split()
                if val:
                    route_info[route_name] = val
            else:
                found = False
            route_index += 1
        if dev_name in out_ifaces:
            out_ifaces[dev_name].update(route_info)
        else:
            out_ifaces[dev_name] = route_info
    return out_ifaces
