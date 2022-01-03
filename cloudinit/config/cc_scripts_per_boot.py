# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Scripts Per Boot
----------------
**Summary:** run per boot scripts

Any scripts in the ``scripts/per-boot`` directory on the datasource will be run
every time the system boots. Scripts will be run in alphabetical order. This
module does not accept any config keys.

**Internal name:** ``cc_scripts_per_boot``

**Module frequency:** always

**Supported distros:** all
"""

import os

from cloudinit import subp
from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS

SCRIPT_SUBDIR = "per-boot"


def handle(name, _cfg, cloud, log, _args):
    # Comes from the following:
    # https://forums.aws.amazon.com/thread.jspa?threadID=96918
    runparts_path = os.path.join(cloud.get_cpath(), "scripts", SCRIPT_SUBDIR)
    try:
        subp.runparts(runparts_path)
    except Exception:
        log.warning(
            "Failed to run module %s (%s in %s)",
            name,
            SCRIPT_SUBDIR,
            runparts_path,
        )
        raise


# vi: ts=4 expandtab
