# Copyright (C) 2011 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Scripts User: Run user scripts"""

import os
from logging import Logger

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module runs all user scripts. User scripts are not specified in the
``scripts`` directory in the datasource, but rather are present in the
``scripts`` dir in the instance configuration. Any cloud-config parts with a
``#!`` will be treated as a script and run. Scripts specified as cloud-config
parts will be run in the order they are specified in the configuration.
This module does not accept any config keys.
"""

meta: MetaSchema = {
    "id": "cc_scripts_user",
    "name": "Scripts User",
    "title": "Run user scripts",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


SCRIPT_SUBDIR = "scripts"


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    # This is written to by the user data handlers
    # Ie, any custom shell scripts that come down
    # go here...
    runparts_path = os.path.join(cloud.get_ipath_cur(), SCRIPT_SUBDIR)
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
