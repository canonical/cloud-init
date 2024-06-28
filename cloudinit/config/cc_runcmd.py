# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Runcmd: run arbitrary commands at rc.local with output to the console"""

import logging
import os

from cloudinit import util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

# The schema definition for each cloud-config module is a strict contract for
# describing supported configuration parameters for each cloud-config section.
# It allows cloud-config to validate and alert users to invalid or ignored
# configuration options before actually attempting to deploy with said
# configuration.

meta: MetaSchema = {
    "id": "cc_runcmd",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["runcmd"],
}  # type: ignore

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "runcmd" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'runcmd' key in configuration", name
        )
        return

    out_fn = os.path.join(cloud.get_ipath("scripts"), "runcmd")
    cmd = cfg["runcmd"]
    try:
        content = util.shellify(cmd)
        util.write_file(out_fn, content, 0o700)
    except Exception as e:
        raise type(e)("Failed to shellify {} into file {}".format(cmd, out_fn))
