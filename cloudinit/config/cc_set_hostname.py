# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

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

    preserve_hostname: <true/false>
    fqdn: <fqdn>
    hostname: <fqdn/hostname>
"""

import os


from cloudinit.atomic_helper import write_json
from cloudinit import util


class SetHostnameError(Exception):
    """Raised when the distro runs into an exception when setting hostname.

    This may happen if we attempt to set the hostname early in cloud-init's
    init-local timeframe as certain services may not be running yet.
    """
    pass


def handle(name, cfg, cloud, log, _args):
    if util.get_cfg_option_bool(cfg, "preserve_hostname", False):
        log.debug(("Configuration option 'preserve_hostname' is set,"
                   " not setting the hostname in module %s"), name)
        return
    (hostname, fqdn) = util.get_hostname_fqdn(cfg, cloud)
    # Check for previous successful invocation of set-hostname

    # set-hostname artifact file accounts for both hostname and fqdn
    # deltas. As such, it's format is different than cc_update_hostname's
    # previous-hostname file which only contains the base hostname.
    # TODO consolidate previous-hostname and set-hostname artifact files and
    # distro._read_hostname implementation so we only validate  one artifact.
    prev_fn = os.path.join(cloud.get_cpath('data'), "set-hostname")
    prev_hostname = {}
    if os.path.exists(prev_fn):
        prev_hostname = util.load_json(util.load_file(prev_fn))
    hostname_changed = (hostname != prev_hostname.get('hostname') or
                        fqdn != prev_hostname.get('fqdn'))
    if not hostname_changed:
        log.debug('No hostname changes. Skipping set-hostname')
        return
    log.debug("Setting the hostname to %s (%s)", fqdn, hostname)
    try:
        cloud.distro.set_hostname(hostname, fqdn)
    except Exception as e:
        msg = "Failed to set the hostname to %s (%s)" % (fqdn, hostname)
        util.logexc(log, msg)
        raise SetHostnameError("%s: %s" % (msg, e))
    write_json(prev_fn, {'hostname': hostname, 'fqdn': fqdn})

# vi: ts=4 expandtab
