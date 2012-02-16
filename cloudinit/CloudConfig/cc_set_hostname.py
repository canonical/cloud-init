# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
#    Author: Scott Moser <scott.moser@canonical.com>
#    Author: Juerg Haefliger <juerg.haefliger@hp.com>
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

import cloudinit.util as util


def handle(_name, cfg, cloud, log, _args):
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug("preserve_hostname is set. not setting hostname")
        return(True)

    (hostname, _fqdn) = util.get_hostname_fqdn(cfg, cloud)
    try:
        set_hostname(hostname, log)
    except Exception:
        util.logexc(log)
        log.warn("failed to set hostname to %s\n", hostname)

    return(True)


def set_hostname(hostname, log):
    util.subp(['hostname', hostname])
    util.write_file("/etc/hostname", "%s\n" % hostname, 0644)
    log.debug("populated /etc/hostname with %s on first boot", hostname)
