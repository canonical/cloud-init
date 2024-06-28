# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Disable EC2 Metadata: Disable AWS EC2 metadata."""

import logging

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_ALWAYS

REJECT_CMD_IF = ["route", "add", "-host", "169.254.169.254", "reject"]
REJECT_CMD_IP = ["ip", "route", "add", "prohibit", "169.254.169.254"]

LOG = logging.getLogger(__name__)

meta: MetaSchema = {
    "id": "cc_disable_ec2_metadata",
    "distros": [ALL_DISTROS],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": ["disable_ec2_metadata"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    disabled = util.get_cfg_option_bool(cfg, "disable_ec2_metadata", False)
    if disabled:
        reject_cmd = None
        if subp.which("ip"):
            reject_cmd = REJECT_CMD_IP
        elif subp.which("ifconfig"):
            reject_cmd = REJECT_CMD_IF
        else:
            LOG.error(
                'Neither "route" nor "ip" command found, unable to '
                "manipulate routing table"
            )
            return
        subp.subp(reject_cmd, capture=False)
    else:
        LOG.debug(
            "Skipping module named %s, disabling the ec2 route not enabled",
            name,
        )
