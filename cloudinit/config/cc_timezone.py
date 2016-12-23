# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Timezone
--------
**Summary:** set system timezone

Set the system timezone. If any args are passed to the module then the first
will be used for the timezone. Otherwise, the module will attempt to retrieve
the timezone from cloud config.

**Internal name:** ``cc_timezone``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    timezone: <timezone>
"""

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE


def handle(name, cfg, cloud, log, args):
    if len(args) != 0:
        timezone = args[0]
    else:
        timezone = util.get_cfg_option_str(cfg, "timezone", False)

    if not timezone:
        log.debug("Skipping module named %s, no 'timezone' specified", name)
        return

    # Let the distro handle settings its timezone
    cloud.distro.set_timezone(timezone)

# vi: ts=4 expandtab
