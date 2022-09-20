# Copyright (C) 2021 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Write Files Deferred: Defer writing certain files"""

from logging import Logger

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.cc_write_files import DEFAULT_DEFER, write_files
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
This module is based on `'Write Files' <write-files>`__, and
will handle all files from the write_files list, that have been
marked as deferred and thus are not being processed by the
write-files module.

*Please note that his module is not exposed to the user through
its own dedicated top-level directive.*
"""
meta: MetaSchema = {
    "id": "cc_write_files_deferred",
    "name": "Write Files Deferred",
    "title": "Defer writing certain files",
    "description": __doc__,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [],
    "activate_by_schema_keys": ["write_files"],
}

# This module is undocumented in our schema docs
__doc__ = ""


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    file_list = cfg.get("write_files", [])
    filtered_files = [
        f
        for f in file_list
        if util.get_cfg_option_bool(f, "defer", DEFAULT_DEFER)
    ]
    if not filtered_files:
        log.debug(
            "Skipping module named %s,"
            " no deferred file defined in configuration",
            name,
        )
        return
    write_files(name, filtered_files, cloud.distro.default_owner)
