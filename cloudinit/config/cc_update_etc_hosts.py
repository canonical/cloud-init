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

from cloudinit import templater
from cloudinit import util

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS


def handle(name, cfg, cloud, log, _args):
    manage_hosts = util.get_cfg_option_str(cfg, "manage_etc_hosts", False)
    if util.translate_bool(manage_hosts, addons=['template']):
        (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            log.warn(("Option 'manage_etc_hosts' was set,"
                     " but no hostname was found"))
            return

        # Render from a template file
        tpl_fn_name = cloud.get_template_filename("hosts.%s" %
                                                  (cloud.distro.osfamily))
        if not tpl_fn_name:
            raise RuntimeError(("No hosts template could be"
                                " found for distro %s") %
                                (cloud.distro.osfamily))

        templater.render_to_file(tpl_fn_name, '/etc/hosts',
                                {'hostname': hostname, 'fqdn': fqdn})

    elif manage_hosts == "localhost":
        (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
        if not hostname:
            log.warn(("Option 'manage_etc_hosts' was set,"
                     " but no hostname was found"))
            return

        log.debug("Managing localhost in /etc/hosts")
        cloud.distro.update_etc_hosts(hostname, fqdn)
    else:
        log.debug(("Configuration option 'manage_etc_hosts' is not set,"
                    " not managing /etc/hosts in module %s"), name)
