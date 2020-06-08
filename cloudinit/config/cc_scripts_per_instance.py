# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Scripts Per Instance
--------------------
**Summary:** run per instance scripts

Any scripts in the ``scripts/per-instance`` directory on the datasource will
be run when a new instance is first booted. Scripts will be run in alphabetical
order. This module does not accept any config keys.

Some cloud platforms change instance-id if a significant change was made to
the system. As a result per-instance scripts will run again.

**Internal name:** ``cc_scripts_per_instance``

**Module frequency:** per instance

**Supported distros:** all
"""

import os

from cloudinit import subp

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

SCRIPT_SUBDIR = 'per-instance'


def handle(name, _cfg, cloud, log, _args):
    # Comes from the following:
    # https://forums.aws.amazon.com/thread.jspa?threadID=96918
    runparts_path = os.path.join(cloud.get_cpath(), 'scripts', SCRIPT_SUBDIR)
    try:
        subp.runparts(runparts_path)
    except Exception:
        log.warning("Failed to run module %s (%s in %s)",
                    name, SCRIPT_SUBDIR, runparts_path)
        raise

# vi: ts=4 expandtab
