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

from cloudinit.distros.parsers.resolv_conf import ResolvConf
from cloudinit.distros.parsers.sys_conf import SysConf

from cloudinit import helpers
from cloudinit import log as logging
from cloudinit import util

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


def _make_sysconfig_bool(val):
    if val:
        return 'yes'
    else:
        return 'no'


class Distro(distros.Distro):
    # See: http://tiny.cc/6r99fw
    clock_conf_fn = "/etc/sysconfig/clock"
    locale_conf_fn = '/etc/sysconfig/i18n'
    systemd_locale_conf_fn = '/etc/locale.conf'
    network_conf_fn = "/etc/sysconfig/network"
    hostname_conf_fn = "/etc/sysconfig/network"
    systemd_hostname_conf_fn = "/etc/hostname"
    network_script_tpl = '/etc/sysconfig/network-scripts/ifcfg-%s'
    resolve_conf_fn = "/etc/resolv.conf"
    tz_local_fn = "/etc/localtime"
    tz_zone_dir = "/usr/share/zoneinfo"

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)
        self.osfamily = 'redhat'

    def install_packages(self, pkglist):
        self.package_command('install', pkgs=pkglist)

    def _adjust_resolve(self, dns_servers, search_servers):
        try:
            r_conf = ResolvConf(util.load_file(self.resolve_conf_fn))
            r_conf.parse()
        except IOError:
            util.logexc(LOG,
                        "Failed at parsing %s reverting to an empty instance",
                        self.resolve_conf_fn)
            r_conf = ResolvConf('')
            r_conf.parse()
        if dns_servers:
            for s in dns_servers:
                try:
                    r_conf.add_nameserver(s)
                except ValueError:
                    util.logexc(LOG, "Failed at adding nameserver %s", s)
        if search_servers:
            for s in search_servers:
                try:
                    r_conf.add_search_domain(s)
                except ValueError:
                    util.logexc(LOG, "Failed at adding search domain %s", s)
        util.write_file(self.resolve_conf_fn, str(r_conf), 0644)

    def _write_network(self, settings):
        # TODO(harlowja) fix this... since this is the ubuntu format
        entries = translate_network(settings)
        LOG.debug("Translated ubuntu style network settings %s into %s",
                  settings, entries)
        # Make the intermediate format as the rhel format...
        nameservers = []
        searchservers = []
        dev_names = entries.keys()
        for (dev, info) in entries.iteritems():
            net_fn = self.network_script_tpl % (dev)
            net_cfg = {
                'DEVICE': dev,
                'NETMASK': info.get('netmask'),
                'IPADDR': info.get('address'),
                'BOOTPROTO': info.get('bootproto'),
                'GATEWAY': info.get('gateway'),
                'BROADCAST': info.get('broadcast'),
                'MACADDR': info.get('hwaddress'),
                'ONBOOT': _make_sysconfig_bool(info.get('auto')),
            }
            self._update_sysconfig_file(net_fn, net_cfg)
            if 'dns-nameservers' in info:
                nameservers.extend(info['dns-nameservers'])
            if 'dns-search' in info:
                searchservers.extend(info['dns-search'])
        if nameservers or searchservers:
            self._adjust_resolve(nameservers, searchservers)
        if dev_names:
            net_cfg = {
                'NETWORKING': _make_sysconfig_bool(True),
            }
            self._update_sysconfig_file(self.network_conf_fn, net_cfg)
        return dev_names

    def _update_sysconfig_file(self, fn, adjustments, allow_empty=False):
        if not adjustments:
            return
        (exists, contents) = self._read_conf(fn)
        updated_am = 0
        for (k, v) in adjustments.items():
            if v is None:
                continue
            v = str(v)
            if len(v) == 0 and not allow_empty:
                continue
            contents[k] = v
            updated_am += 1
        if updated_am:
            lines = [
                str(contents),
            ]
            if not exists:
                lines.insert(0, util.make_header())
            util.write_file(fn, "\n".join(lines) + "\n", 0644)

    def _dist_uses_systemd(self):
        # Fedora 18 and RHEL 7 were the first adopters in their series
        (dist, vers) = util.system_info()['dist'][:2]
        major = (int)(vers.split('.')[0])
        return ((dist.startswith('Red Hat Enterprise Linux') and major >= 7)
                or (dist.startswith('Fedora') and major >= 18))

    def apply_locale(self, locale, out_fn=None):
        if self._dist_uses_systemd():
            if not out_fn:
                out_fn = self.systemd_locale_conf_fn
            out_fn = self.systemd_locale_conf_fn
        else:
            if not out_fn:
                out_fn = self.locale_conf_fn
        locale_cfg = {
            'LANG': locale,
        }
        self._update_sysconfig_file(out_fn, locale_cfg)

    def _write_hostname(self, hostname, out_fn):
        if self._dist_uses_systemd():
            util.subp(['hostnamectl', 'set-hostname', str(hostname)])
        else:
            host_cfg = {
                'HOSTNAME': hostname,
            }
            self._update_sysconfig_file(out_fn, host_cfg)

    def _select_hostname(self, hostname, fqdn):
        # See: http://bit.ly/TwitgL
        # Should be fqdn if we can use it
        if fqdn:
            return fqdn
        return hostname

    def _read_system_hostname(self):
        if self._dist_uses_systemd():
            host_fn = self.systemd_hostname_conf_fn
        else:
            host_fn = self.hostname_conf_fn
        return (host_fn, self._read_hostname(host_fn))

    def _read_hostname(self, filename, default=None):
        if self._dist_uses_systemd():
            (out, _err) = util.subp(['hostname'])
            if len(out):
                return out
            else:
                return default
        else:
            (_exists, contents) = self._read_conf(filename)
            if 'HOSTNAME' in contents:
                return contents['HOSTNAME']
            else:
                return default

    def _read_conf(self, fn):
        exists = False
        try:
            contents = util.load_file(fn).splitlines()
            exists = True
        except IOError:
            contents = []
        return (exists,
                SysConf(contents))

    def _bring_up_interfaces(self, device_names):
        if device_names and 'all' in device_names:
            raise RuntimeError(('Distro %s can not translate '
                                'the device name "all"') % (self.name))
        return distros.Distro._bring_up_interfaces(self, device_names)

    def set_timezone(self, tz):
        # TODO(harlowja): move this code into
        # the parent distro...
        tz_file = os.path.join(self.tz_zone_dir, str(tz))
        if not os.path.isfile(tz_file):
            raise RuntimeError(("Invalid timezone %s,"
                                " no file found at %s") % (tz, tz_file))
        if self._dist_uses_systemd():
            # Currently, timedatectl complains if invoked during startup
            # so for compatibility, create the link manually.
            util.del_file(self.tz_local_fn)
            util.sym_link(tz_file, self.tz_local_fn)
        else:
            # Adjust the sysconfig clock zone setting
            clock_cfg = {
                'ZONE': str(tz),
            }
            self._update_sysconfig_file(self.clock_conf_fn, clock_cfg)
            # This ensures that the correct tz will be used for the system
            util.copy(tz_file, self.tz_local_fn)

    def package_command(self, command, args=None, pkgs=None):
        if pkgs is None:
            pkgs = []

        cmd = ['yum']
        # If enabled, then yum will be tolerant of errors on the command line
        # with regard to packages.
        # For example: if you request to install foo, bar and baz and baz is
        # installed; yum won't error out complaining that baz is already
        # installed.
        cmd.append("-t")
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


# This is a util function to translate a ubuntu /etc/network/interfaces 'blob'
# to a rhel equiv. that can then be written to /etc/sysconfig/network-scripts/
# TODO(harlowja) remove when we have python-netcf active...
def translate_network(settings):
    # Get the standard cmd, args from the ubuntu format
    entries = []
    for line in settings.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        split_up = line.split(None, 1)
        if len(split_up) <= 1:
            continue
        entries.append(split_up)
    # Figure out where each iface section is
    ifaces = []
    consume = {}
    for (cmd, args) in entries:
        if cmd == 'iface':
            if consume:
                ifaces.append(consume)
                consume = {}
            consume[cmd] = args
        else:
            consume[cmd] = args
    # Check if anything left over to consume
    absorb = False
    for (cmd, args) in consume.iteritems():
        if cmd == 'iface':
            absorb = True
    if absorb:
        ifaces.append(consume)
    # Now translate
    real_ifaces = {}
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
        iface_info = {}
        if len(iface_details) >= 3:
            proto_type = iface_details[2].strip().lower()
            # Seems like this can be 'loopback' which we don't
            # really care about
            if proto_type in ['dhcp', 'static']:
                iface_info['bootproto'] = proto_type
        # These can just be copied over
        for k in ['netmask', 'address', 'gateway', 'broadcast']:
            if k in info:
                val = info[k].strip().lower()
                if val:
                    iface_info[k] = val
        # Name server info provided??
        if 'dns-nameservers' in info:
            iface_info['dns-nameservers'] = info['dns-nameservers'].split()
        # Name server search info provided??
        if 'dns-search' in info:
            iface_info['dns-search'] = info['dns-search'].split()
        # Is any mac address spoofing going on??
        if 'hwaddress' in info:
            hw_info = info['hwaddress'].lower().strip()
            hw_split = hw_info.split(None, 1)
            if len(hw_split) == 2 and hw_split[0].startswith('ether'):
                hw_addr = hw_split[1]
                if hw_addr:
                    iface_info['hwaddress'] = hw_addr
        real_ifaces[dev_name] = iface_info
    # Check for those that should be started on boot via 'auto'
    for (cmd, args) in entries:
        if cmd == 'auto':
            # Seems like auto can be like 'auto eth0 eth0:1' so just get the
            # first part out as the device name
            args = args.split(None)
            if not args:
                continue
            dev_name = args[0].strip().lower()
            if dev_name in real_ifaces:
                real_ifaces[dev_name]['auto'] = True
    return real_ifaces
