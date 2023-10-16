# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Scripts Per Instance: Run per instance scripts"""

import logging
import os

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Any scripts in the ``scripts/per-instance`` directory on the datasource will
be run when a new instance is first booted. Scripts will be run in alphabetical
order. This module does not accept any config keys.

Some cloud platforms change instance-id if a significant change was made to
the system. As a result per-instance scripts will run again.
"""

meta: MetaSchema = {
    "id": "cc_scripts_per_instance",
    "name": "Scripts Per Instance",
    "title": "Run per instance scripts",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)
LOG = logging.getLogger(__name__)

SCRIPT_SUBDIR = "per-instance"


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # Comes from the following:
    # https://forums.aws.amazon.com/thread.jspa?threadID=96918
    runparts_path = os.path.join(cloud.get_cpath(), "scripts", SCRIPT_SUBDIR)
    try:
        subp.runparts(runparts_path)
    except Exception:
        LOG.warning(
            "Failed to run module %s (%s in %s)",
            name,
            SCRIPT_SUBDIR,
            runparts_path,
        )
        raise
