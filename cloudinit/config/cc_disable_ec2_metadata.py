# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Disable EC2 Metadata
--------------------
**Summary:** disable aws ec2 metadata

This module can disable the ec2 datasource by rejecting the route to
``169.254.169.254``, the usual route to the datasource. This module is disabled
by default.

**Internal name:** ``cc_disable_ec2_metadata``

**Module frequency:** per always

**Supported distros:** all

**Config keys**::

    disable_ec2_metadata: <true/false>
"""

from cloudinit import util

from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS

REJECT_CMD_IF = ['route', 'add', '-host', '169.254.169.254', 'reject']
REJECT_CMD_IPRTADD = ['ip', 'route', 'add', 'prohibit', '169.254.169.254']
REJECT_CMD_IPRTCHG = ['ip', 'route', 'change', 'prohibit', '169.254.169.254']


def handle(name, cfg, _cloud, log, _args):
    disabled = util.get_cfg_option_bool(cfg, "disable_ec2_metadata", False)
    if disabled:
        if util.which('ip'):
            # ip-route-add requires a route not already exist and and
            # ip-route-change requires a route already exist. EAFP.
            try:
                util.subp(REJECT_CMD_IPRTCHG, capture=False)
            except util.ProcessExecutionError:
                util.subp(REJECT_CMD_IPRTADD, capture=False)
        elif util.which('ifconfig'):
            util.subp(REJECT_CMD_IF, capture=False)
        else:
            log.error(('Neither "route" nor "ip" command found, unable to '
                       'manipulate routing table'))
            return
    else:
        log.debug(("Skipping module named %s,"
                   " disabling the ec2 route not enabled"), name)

# vi: ts=4 expandtab
