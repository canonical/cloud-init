# Copyright (C) 2014 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Scripts Vendor
--------------
**Summary:** run vendor scripts

Any scripts in the ``scripts/vendor`` directory in the datasource will be run
when a new instance is first booted. Scripts will be run in alphabetical order.
Vendor scripts can be run with an optional prefix specified in the ``prefix``
entry under the ``vendor_data`` config key.

**Internal name:** ``cc_scripts_vendor``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    vendor_data:
        prefix: <vendor data prefix>
"""

import os

from cloudinit import util

from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

SCRIPT_SUBDIR = 'vendor'


def handle(name, cfg, cloud, log, _args):
    # This is written to by the vendor data handlers
    # any vendor data shell scripts get placed in runparts_path
    runparts_path = os.path.join(cloud.get_ipath_cur(), 'scripts',
                                 SCRIPT_SUBDIR)

    prefix = util.get_cfg_by_path(cfg, ('vendor_data', 'prefix'), [])

    try:
        util.runparts(runparts_path, exe_prefix=prefix)
    except Exception:
        log.warn("Failed to run module %s (%s in %s)",
                 name, SCRIPT_SUBDIR, runparts_path)
        raise

# vi: ts=4 expandtab
