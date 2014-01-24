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


# This is a util function to translate debian based distro interface blobs as
# given in /etc/network/interfaces to an *somewhat* agnostic format for
# distributions that use other formats.
#
# TODO(harlowja) remove when we have python-netcf active...
#
# The format is the following:
# {
#    <device-name>: {
#        # All optional (if not existent in original format)
#        "netmask": <ip>,
#        "broadcast": <ip>,
#        "gateway": <ip>,
#        "address": <ip>,
#        "bootproto": "static"|"dhcp",
#        "dns-search": <hostname>,
#        "hwaddress": <mac-address>,
#        "auto": True (or non-existent),
#        "dns-nameservers": [<ip/hostname>, ...],
#    }
# }
#
# Things to note, comments are removed, if a ubuntu/debian interface is
# marked as auto then only then first segment (?) is retained, ie
# 'auto eth0 eth0:1' just marks eth0 as auto (not eth0:1).
#
# Example input:
#
# auto lo
# iface lo inet loopback
#
# auto eth0
# iface eth0 inet static
#         address 10.0.0.1
#         netmask 255.255.252.0
#         broadcast 10.0.0.255
#         gateway 10.0.0.2
#         dns-nameservers 98.0.0.1 98.0.0.2
#
# Example output:
# {
#     "lo": {
#         "auto": true
#     },
#     "eth0": {
#         "auto": true,
#         "dns-nameservers": [
#             "98.0.0.1",
#             "98.0.0.2"
#         ],
#         "broadcast": "10.0.0.255",
#         "netmask": "255.255.252.0",
#         "bootproto": "static",
#         "address": "10.0.0.1",
#         "gateway": "10.0.0.2"
#     }
# }

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
