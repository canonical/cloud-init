# Copyright (C) 2014 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Scripts Vendor: Run vendor scripts"""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_scripts_vendor",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)

SCRIPT_SUBDIR = "vendor"


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    # This is written to by the vendor data handlers
    # any vendor data shell scripts get placed in runparts_path
    runparts_path = os.path.join(
        cloud.get_ipath_cur(), "scripts", SCRIPT_SUBDIR
    )

    prefix = util.get_cfg_by_path(cfg, ("vendor_data", "prefix"), [])

    try:
        subp.runparts(runparts_path, exe_prefix=prefix)
    except Exception:
        LOG.warning(
            "Failed to run module %s (%s in %s)",
            name,
            SCRIPT_SUBDIR,
            runparts_path,
        )
        raise
