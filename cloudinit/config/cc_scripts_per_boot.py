# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Scripts Per Boot: Run per boot scripts"""

import os
from logging import Logger

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

frequency = PER_ALWAYS
MODULE_DESCRIPTION = """\
Any scripts in the ``scripts/per-boot`` directory on the datasource will be run
every time the system boots. Scripts will be run in alphabetical order. This
module does not accept any config keys.
"""


meta: MetaSchema = {
    "id": "cc_scripts_per_boot",
    "name": "Scripts Per Boot",
    "title": "Run per boot scripts",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": frequency,
    "examples": [],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)

SCRIPT_SUBDIR = "per-boot"


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
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
