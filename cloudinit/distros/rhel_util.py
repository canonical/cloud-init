# vi: ts=4 expandtab
#
#    Copyright (C) 2012 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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
#

from cloudinit.distros.parsers.resolv_conf import ResolvConf
from cloudinit.distros.parsers.sys_conf import SysConf

from cloudinit import log as logging
from cloudinit import util

LOG = logging.getLogger(__name__)


# This is a util function to translate Debian based distro interface blobs as
# given in /etc/network/interfaces to an equivalent format for distributions
# that use ifcfg-* style (Red Hat and SUSE).
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


# Helper function to update a RHEL/SUSE /etc/sysconfig/* file
def update_sysconfig_file(fn, adjustments, allow_empty=False):
    if not adjustments:
        return
    (exists, contents) = read_sysconfig_file(fn)
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


# Helper function to read a RHEL/SUSE /etc/sysconfig/* file
def read_sysconfig_file(fn):
    exists = False
    try:
        contents = util.load_file(fn).splitlines()
        exists = True
    except IOError:
        contents = []
    return (exists, SysConf(contents))


# Helper function to update RHEL/SUSE /etc/resolv.conf
def update_resolve_conf_file(fn, dns_servers, search_servers):
    try:
        r_conf = ResolvConf(util.load_file(fn))
        r_conf.parse()
    except IOError:
        util.logexc(LOG, "Failed at parsing %s reverting to an empty "
                    "instance", fn)
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
    util.write_file(fn, str(r_conf), 0644)
