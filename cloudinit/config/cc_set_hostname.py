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
Set Hostname
------------
**Summary:** set hostname and fqdn

This module handles setting the system hostname and fqdn. If
``preserve_hostname`` is set, then the hostname will not be altered.

A hostname and fqdn can be provided by specifying a full domain name under the
``fqdn`` key. Alternatively, a hostname can be specified using the ``hostname``
key, and the fqdn of the cloud wil be used. If a fqdn specified with the
``hostname`` key, it will be handled properly, although it is better to use
the ``fqdn`` config key. If both ``fqdn`` and ``hostname`` are set, ``fqdn``
will be used.

**Internal name:** per instance

**Supported distros:** all

**Config keys**::

    perserve_hostname: <true/false>
    fqdn: <fqdn>
    hostname: <fqdn/hostname>
"""

from cloudinit import util


def handle(name, cfg, cloud, log, _args):
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug(("Configuration option 'preserve_hostname' is set,"
                   " not setting the hostname in module %s"), name)
        return

    (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
    try:
        log.debug("Setting the hostname to %s (%s)", fqdn, hostname)
        cloud.distro.set_hostname(hostname, fqdn)
    except Exception:
        util.logexc(log, "Failed to set the hostname to %s (%s)", fqdn,
                    hostname)
        raise
