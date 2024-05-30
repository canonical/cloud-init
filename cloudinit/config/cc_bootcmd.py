# Copyright (C) 2009-2011 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Chad Smith <chad.smith@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""Bootcmd: run arbitrary commands early in the boot process."""

import logging

from cloudinit import subp, temp_utils, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_ALWAYS

LOG = logging.getLogger(__name__)

frequency = PER_ALWAYS


meta: MetaSchema = {
    "id": "cc_bootcmd",
    "distros": ["all"],
    "frequency": PER_ALWAYS,
    "activate_by_schema_keys": ["bootcmd"],
}  # type: ignore


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:

    if "bootcmd" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'bootcmd' key in configuration", name
        )
        return

    with temp_utils.ExtendedTemporaryFile(suffix=".sh") as tmpf:
        try:
            content = util.shellify(cfg["bootcmd"])
            tmpf.write(util.encode_text(content))
            tmpf.flush()
        except Exception as e:
            util.logexc(LOG, "Failed to shellify bootcmd: %s", str(e))
            raise

        try:
            iid = cloud.get_instance_id()
            env = {"INSTANCE_ID": str(iid)} if iid else {}
            subp.subp(["/bin/sh", tmpf.name], update_env=env, capture=False)
        except Exception:
            util.logexc(LOG, "Failed to run bootcmd module %s", name)
            raise
