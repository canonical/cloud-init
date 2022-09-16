# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Timezone: Set the system timezone"""

from logging import Logger

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = """\
Sets the system timezone based on the value provided.
"""

meta: MetaSchema = {
    "id": "cc_timezone",
    "name": "Timezone",
    "title": "Set the system timezone",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        "timezone: US/Eastern",
    ],
    "activate_by_schema_keys": ["timezone"],
}

__doc__ = get_meta_doc(meta)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if len(args) != 0:
        timezone = args[0]
    else:
        timezone = util.get_cfg_option_str(cfg, "timezone", False)

    if not timezone:
        log.debug("Skipping module named %s, no 'timezone' specified", name)
        return

    # Let the distro handle settings its timezone
    cloud.distro.set_timezone(timezone)


# vi: ts=4 expandtab
