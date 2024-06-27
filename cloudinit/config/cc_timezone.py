# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Timezone: Set the system timezone"""

import logging

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_timezone",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        "timezone: US/Eastern",
    ],
    "activate_by_schema_keys": ["timezone"],
}  # type: ignore

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if len(args) != 0:
        timezone = args[0]
    else:
        timezone = util.get_cfg_option_str(cfg, "timezone", False)

    if not timezone:
        LOG.debug("Skipping module named %s, no 'timezone' specified", name)
        return

    # Let the distro handle settings its timezone
    cloud.distro.set_timezone(timezone)
