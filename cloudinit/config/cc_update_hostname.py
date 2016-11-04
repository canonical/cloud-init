# vi: ts=4 expandtab
#
#    Copyright (C) 2011 Canonical Ltd.
#    Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
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

"""
Update Hostname
---------------
**Summary:** update hostname and fqdn

This module will update the system hostname and fqdn. If ``preserve_hostname``
is set, then the hostname will not be altered.

.. note::
    for instructions on specifying hostname and fqdn, see documentation for
    ``cc_set_hostname``

**Internal name:** ``cc_update_hostname``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    preserve_hostname: <true/false>
    fqdn: <fqdn>
    hostname: <fqdn/hostname>
"""

import os

from cloudinit.settings import PER_ALWAYS
from cloudinit import util

frequency = PER_ALWAYS


def handle(name, cfg, cloud, log, _args):
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug(("Configuration option 'preserve_hostname' is set,"
                   " not updating the hostname in module %s"), name)
        return

    (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
    try:
        prev_fn = os.path.join(cloud.get_cpath('data'), "previous-hostname")
        log.debug("Updating hostname to %s (%s)", fqdn, hostname)
        cloud.distro.update_hostname(hostname, fqdn, prev_fn)
    except Exception:
        util.logexc(log, "Failed to update the hostname to %s (%s)", fqdn,
                    hostname)
        raise
