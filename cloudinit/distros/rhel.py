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
from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)

NETWORK_FN_TPL = '/etc/sysconfig/network-scripts/ifcfg-%s'


class Distro(distros.Distro):

    def __init__(self, name, cfg, paths):
        distros.Distro.__init__(self, name, cfg, paths)
    
    def install_packages(self, pkglist):
        self.package_command('install', pkglist)

    def _write_network(self, settings):
        # TODO fix this... since this is the ubuntu format
        entries = translate_network(settings)
        LOG.debug("Translated ubuntu style network settings %s into %s",
                  settings, entries)
        # Make the intermediate format as the rhel format...
        for (dev, info) in entries.iteritems():
            lines = []
            lines.append("DEVICE=%s" % (dev))
            boot_proto = info.get('bootproto')
            if boot_proto:
                lines.append("BOOTPROTO=%s" % (boot_proto))
            net_mask = info.get('netmask')
            if net_mask:
                lines.append("NETMASK=%s" % (net_mask))
            addr = info.get('address')
            if addr:
                lines.append("IPADDR=%s" % (addr))
            if info.get('auto'):
                lines.append("ONBOOT=yes")
            else:
                lines.append("ONBOOT=no")
            gtway = info.get('gateway')
            if gtway:
                lines.append("GATEWAY=%s" % (gtway))
            bcast = info.get('broadcast')
            if bcast:
                lines.append("BROADCAST=%s" % (bcast))
            mac_addr = info.get('hwaddress')
            if mac_addr:
                lines.append("MACADDR=%s" % (mac_addr))
            lines.insert(0, '# Created by cloud-init')
            contents = "\n".join(lines)
            net_fn = NETWORK_FN_TPL % (dev)
            util.write_file(self._paths.join(False, net_fn), contents, 0644)

    def set_hostname(self, hostname):
        out_fn = self._paths.join(False, '/etc/sysconfig/network')
        self._write_hostname(hostname, out_fn)
        if out_fn == '/etc/sysconfig/network':
            # Only do this if we are running in non-adjusted root mode
            LOG.debug("Setting hostname to %s", hostname)
            util.subp(['hostname', hostname])

    def _write_hostname(self, hostname, out_fn):
        old_contents = []
        if os.path.isfile(out_fn):
            old_contents = self._read_conf(out_fn)
        # Update the 'HOSTNAME' if it exists instead of appending
        new_contents = []
        adjusted = False
        for entry in old_contents:
            if not entry:
                continue
            if len(entry) == 1:
                new_contents.append(entry[0])
                continue
            (cmd, args) = entry
            cmd_c = cmd.strip().lower()
            if cmd_c == 'hostname':
                args = "%s" % (hostname)
                adjusted = True
            new_contents.append("=".join([cmd, args]))
        # Guess not found, append it
        if not adjusted:
            new_contents.append("# Added by cloud-init")
            new_contents.append("HOSTNAME=%s" % (hostname))
        contents = "\n".join(new_contents)
        util.write_file(out_fn, contents, 0644)

    def update_hostname(self, hostname, prev_file):
        hostname_prev = self._read_hostname(prev_file)
        read_fn = self._paths.join(True, "/etc/sysconfig/network")
        hostname_in_sys = self._read_hostname(read_fn)
        update_files = []
        if not hostname_prev or hostname_prev != hostname:
            update_files.append(prev_file)
        if (not hostname_in_sys or
            (hostname_in_sys == hostname_prev and hostname_in_sys != hostname)):
            write_fn = self._paths.join(False, "/etc/sysconfig/network")
            update_files.append(write_fn)
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
        contents = self._read_conf(filename)
        for c in contents:
            if len(c) != 2:
                continue
            (cmd, args) = c
            cmd_c = cmd.lower().strip()
            if cmd_c == 'hostname':
                args_c = args.strip()
                if args_c:
                    return args_c
        return default

    def _read_conf(self, filename):
        contents = util.load_file(filename, quiet=True)
        conf_lines = []
        for line in contents.splitlines():
            c_line = line.strip()
            if not c_line or c_line.startswith("#"):
                conf_lines.append([line])
                continue
            # Handle inline comments
            c_pos = c_line.find("#")
            if c_pos != -1:
                c_line = c_line[0:c_pos].strip()
            if not c_line:
                conf_lines.append([line])
                continue
            # Format should be CMD=ARG1 ARG2...
            pieces = c_line.split("=", 1)
            if not pieces or len(pieces) == 1:
                conf_lines.append([line])
                continue
            (cmd, args) = pieces
            cmd = cmd.strip()
            conf_lines.append([cmd, args])
        return conf_lines

    def set_timezone(self, tz):
        tz_file = os.path.join("/usr/share/zoneinfo", tz)
        if not os.path.isfile(tz_file):
            raise Exception(("Invalid timezone %s,"
                             " no file found at %s") % (tz, tz_file))
        # Adjust the sysconfig clock zone setting
        read_fn = self._paths.join(True, "/etc/sysconfig/clock")
        old_contents = self._read_conf(read_fn)
        new_contents = []
        zone_added = False
        # Update the 'ZONE' if it exists instead of appending
        for entry in old_contents:
            if not entry:
                continue
            if len(entry) == 1:
                new_contents.append(entry[0])
                continue
            (cmd, args) = entry
            cmd_c = cmd.lower().strip()
            if cmd_c == 'zone':
                args = '"%s"' % (tz)
                zone_added = True
            new_contents.append("=".join([cmd, args]))
        # Guess not found, append it
        if not zone_added:
            new_contents.append("# Added by cloud-init")
            new_contents.append('ZONE="%s"' % (tz))
        tz_contents = "\n".join(new_contents)
        write_fn = self._paths.join(False, "/etc/sysconfig/clock")
        util.write_file(write_fn, tz_contents)
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
        
        
# This is a util function to translate a ubuntu /etc/network/interfaces 'blob'
# to a rhel equiv. that can then be written to /etc/sysconfig/network-scripts/
# TODO remove when we have python-netcf active...
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
