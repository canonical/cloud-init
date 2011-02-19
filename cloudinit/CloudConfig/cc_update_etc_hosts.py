# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#
#    Author: Scott Moser <scott.moser@canonical.com>
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

frequency = per_always

def handle(name,cfg,cloud,log,args):
    if not util.get_cfg_option_bool(cfg,"manage_etc_hosts",False):
        log.debug("manage_etc_hosts is not set. not modifying /etc/hosts")
        return

    try:
        hostname = util.get_cfg_option_str(cfg,"hostname",cloud.get_hostname())
        if not hostname:
            hostname = cloud.get_hostname()

        if not hostname:
            log.info("manage_etc_hosts was set, but no hostname found")
            return

        util.render_to_file('hosts', '/etc/hosts', { 'hostname' : hostname })

    except Exception as e:
        log.warn("failed to update /etc/hosts")
        raise
