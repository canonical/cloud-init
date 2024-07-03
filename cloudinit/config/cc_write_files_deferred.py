# Copyright (C) 2021 Canonical Ltd.
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Write Files Deferred: Defer writing certain files"""

import logging

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.cc_write_files import DEFAULT_DEFER, write_files
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_write_files_deferred",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["write_files"],
}  # type: ignore

# This module is undocumented in our schema docs
LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    file_list = cfg.get("write_files", [])
    filtered_files = [
        f
        for f in file_list
        if util.get_cfg_option_bool(f, "defer", DEFAULT_DEFER)
    ]
    if not filtered_files:
        LOG.debug(
            "Skipping module named %s,"
            " no deferred file defined in configuration",
            name,
        )
        return
    write_files(name, filtered_files, cloud.distro.default_owner)
