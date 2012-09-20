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
from cloudinit import version

from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)

NETWORK_FN_TPL = '/etc/sysconfig/network-scripts/ifcfg-%s'

# See: http://tiny.cc/6r99fw
# For what alot of these files that are being written
# are and the format of them

# This library is used to parse/write
# out the various sysconfig files edited
#
# It has to be slightly modified though
# to ensure that all values are quoted
# since these configs are usually sourced into
# bash scripts...
from configobj import ConfigObj

# See: http://tiny.cc/oezbgw
D_QUOTE_CHARS = {
    "\"": "\\\"",
    "(": "\\(",
    ")": "\\)",
    "$": '\$',
    '`': '\`',
}

def _make_sysconfig_bool(val):
    if val:
        return 'yes'
    else:
        return 'no'


class Distro(distros.Distro):

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
        # This will be used to restrict certain
        # calls from repeatly happening (when they
        # should only happen say once per instance...)
        self._runner = helpers.Runners(paths)

    def install_packages(self, pkglist):
        self.package_command('install', pkglist)

    def _write_resolve(self, dns_servers, search_servers):
        contents = []
        if dns_servers:
            for s in dns_servers:
                contents.append("nameserver %s" % (s))
        if search_servers:
            contents.append("search %s" % (" ".join(search_servers)))
        if contents:
            contents.insert(0, '# Created by cloud-init')
            util.write_file("/etc/resolv.conf", "\n".join(contents), 0644)

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
            net_fn = NETWORK_FN_TPL % (dev)
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
            self._write_resolve(nameservers, searchservers)
        if dev_names:
            net_cfg = {
                'NETWORKING': _make_sysconfig_bool(True),
            }
            self._update_sysconfig_file("/etc/sysconfig/network", net_cfg)
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
            lines = contents.write()
            if not exists:
                ci_ver = version.version_string()
                lines.insert(0, '# Created by cloud-init v. %s' % (ci_ver))
            util.write_file(fn, "\n".join(lines), 0644)

    def set_hostname(self, hostname):
        self._write_hostname(hostname, '/etc/sysconfig/network')
        LOG.debug("Setting hostname to %s", hostname)
        util.subp(['hostname', hostname])

    def apply_locale(self, locale, out_fn=None):
        if not out_fn:
            out_fn = '/etc/sysconfig/i18n'
        locale_cfg = {
            'LANG': locale,
        }
        self._update_sysconfig_file(out_fn, locale_cfg)

    def _write_hostname(self, hostname, out_fn):
        host_cfg = {
            'HOSTNAME':  hostname,
        }
        self._update_sysconfig_file(out_fn, host_cfg)

    def update_hostname(self, hostname, prev_file):
        hostname_prev = self._read_hostname(prev_file)
        hostname_in_sys = self._read_hostname("/etc/sysconfig/network")
        update_files = []
        if not hostname_prev or hostname_prev != hostname:
            update_files.append(prev_file)
        if (not hostname_in_sys or
            (hostname_in_sys == hostname_prev
             and hostname_in_sys != hostname)):
            update_files.append("/etc/sysconfig/network")
        for fn in update_files:
            try:
                self._write_hostname(hostname, fn)
            except:
                util.logexc(LOG, "Failed to write hostname %s to %s",
                            hostname, fn)
        if (hostname_in_sys and hostname_prev and
            hostname_in_sys != hostname_prev):
            LOG.debug(("%s differs from /etc/sysconfig/network."
                        " Assuming user maintained hostname."), prev_file)
        if "/etc/sysconfig/network" in update_files:
            # Only do this if we are running in non-adjusted root mode
            LOG.debug("Setting hostname to %s", hostname)
            util.subp(['hostname', hostname])

    def _read_hostname(self, filename, default=None):
        (_exists, contents) = self._read_conf(filename)
        if 'HOSTNAME' in contents:
            return contents['HOSTNAME']
        else:
            return default

    def _read_conf(self, fn):
        exists = False
        if os.path.isfile(fn):
            contents = util.load_file(fn).splitlines()
            exists = True
        else:
            contents = []
        return (exists, QuotingConfigObj(contents))

    def set_timezone(self, tz):
        tz_file = os.path.join("/usr/share/zoneinfo", tz)
        if not os.path.isfile(tz_file):
            raise RuntimeError(("Invalid timezone %s,"
                                " no file found at %s") % (tz, tz_file))
        # Adjust the sysconfig clock zone setting
        clock_cfg = {
            'ZONE': tz,
        }
        self._update_sysconfig_file("/etc/sysconfig/clock", clock_cfg)
        # This ensures that the correct tz will be used for the system
        util.copy(tz_file, self._paths.join(False, "/etc/localtime"))

    def package_command(self, command, args=None):
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
        cmd.append(command)
        if args:
            cmd.extend(args)
        # Allow the output of this to flow outwards (ie not be captured)
        util.subp(cmd, capture=False)

    def update_package_sources(self):
        self._runner.run("update-sources", self.package_command,
                         ["makecache"], freq=PER_INSTANCE)


# This class helps adjust the configobj
# writing to ensure that when writing a k/v
# on a line, that they are properly quoted
# and have no spaces between the '=' sign.
# - This is mainly due to the fact that
# the sysconfig scripts are often sourced
# directly into bash/shell scripts so ensure
# that it works for those types of use cases.
class QuotingConfigObj(ConfigObj):
    def __init__(self, lines):
        ConfigObj.__init__(self, lines,
                           interpolation=False,
                           write_empty_values=True)

    def _quote_posix(self, text):
        if not text:
            return ''
        for (k, v) in D_QUOTE_CHARS.iteritems():
            text = text.replace(k, v)
        return '"%s"' % (text)

    def _quote_special(self, text):
        if text.lower() in ['yes', 'no', 'true', 'false']:
            return text
        else:
            return self._quote_posix(text)

    def _write_line(self, indent_string, entry, this_entry, comment):
        # Ensure it is formatted fine for
        # how these sysconfig scripts are used
        val = self._decode_element(self._quote(this_entry))
        # Single quoted strings should
        # always work.
        if not val.startswith("'"):
            # Perform any special quoting
            val = self._quote_special(val)
        key = self._decode_element(self._quote(entry, multiline=False))
        cmnt = self._decode_element(comment)
        return '%s%s%s%s%s' % (indent_string,
                               key,
                               "=",
                               val,
                               cmnt)


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
