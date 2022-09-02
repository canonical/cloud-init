# Copyright (C) 2014 Canonical Ltd.
#
# Author: Ben Howard <ben.howard@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Scripts Vendor: Run vendor scripts"""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
On select Datasources, vendors have a channel for the consumption
of all supported user data types via a special channel called
vendor data. Any scripts in the ``scripts/vendor`` directory in the datasource
will be run when a new instance is first booted. Scripts will be run in
alphabetical order. This module allows control over the execution of
vendor data.
"""

meta: MetaSchema = {
    "id": "cc_scripts_vendor",
    "name": "Scripts Vendor",
    "title": "Run vendor scripts",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            vendor_data:
              enabled: true
              prefix: /usr/bin/ltrace
            """
        ),
        dedent(
            """\
            vendor_data:
              enabled: true
              prefix: [timeout, 30]
            """
        ),
        dedent(
            """\
            # Vendor data will not be processed
            vendor_data:
              enabled: false
            """
        ),
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


SCRIPT_SUBDIR = "vendor"


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    # This is written to by the vendor data handlers
    # any vendor data shell scripts get placed in runparts_path
    runparts_path = os.path.join(
        cloud.get_ipath_cur(), "scripts", SCRIPT_SUBDIR
    )

    prefix = util.get_cfg_by_path(cfg, ("vendor_data", "prefix"), [])

    try:
        subp.runparts(runparts_path, exe_prefix=prefix)
    except Exception:
        log.warning(
            "Failed to run module %s (%s in %s)",
            name,
            SCRIPT_SUBDIR,
            runparts_path,
        )
        raise


# vi: ts=4 expandtab
