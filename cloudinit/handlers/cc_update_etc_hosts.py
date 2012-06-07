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
from cloudinit.CloudConfig import per_always
import StringIO

frequency = per_always


def handle(_name, cfg, cloud, log, _args):
    (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)

    manage_hosts = util.get_cfg_option_str(cfg, "manage_etc_hosts", False)
    if manage_hosts in ("True", "true", True, "template"):
        # render from template file
        try:
            if not hostname:
                log.info("manage_etc_hosts was set, but no hostname found")
                return

            util.render_to_file('hosts', '/etc/hosts',
                                {'hostname': hostname, 'fqdn': fqdn})
        except Exception:
            log.warn("failed to update /etc/hosts")
            raise
    elif manage_hosts == "localhost":
        log.debug("managing 127.0.1.1 in /etc/hosts")
        update_etc_hosts(hostname, fqdn, log)
        return
    else:
        if manage_hosts not in ("False", False):
            log.warn("Unknown value for manage_etc_hosts.  Assuming False")
        else:
            log.debug("not managing /etc/hosts")


def update_etc_hosts(hostname, fqdn, _log):
    with open('/etc/hosts', 'r') as etchosts:
        header = "# Added by cloud-init\n"
        hosts_line = "127.0.1.1\t%s %s\n" % (fqdn, hostname)
        need_write = False
        need_change = True
        new_etchosts = StringIO.StringIO()
        for line in etchosts:
            split_line = [s.strip() for s in line.split()]
            if len(split_line) < 2:
                new_etchosts.write(line)
                continue
            if line == header:
                continue
            ip, hosts = split_line[0], split_line[1:]
            if ip == "127.0.1.1":
                if sorted([hostname, fqdn]) == sorted(hosts):
                    need_change = False
                if need_change == True:
                    line = "%s%s" % (header, hosts_line)
                    need_change = False
                    need_write = True
            new_etchosts.write(line)
        etchosts.close()
        if need_change == True:
            new_etchosts.write("%s%s" % (header, hosts_line))
            need_write = True
        if need_write == True:
            new_etcfile = open('/etc/hosts', 'wb')
            new_etcfile.write(new_etchosts.getvalue())
            new_etcfile.close()
        new_etchosts.close()
    return
