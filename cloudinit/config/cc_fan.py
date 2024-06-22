# Copyright (C) 2015 Canonical Ltd.
#
# Author: Scott Moser <scott.moser@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Fan: Configure ubuntu fan networking"""

import logging

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_fan",
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["fan"],
}  # type: ignore

LOG = logging.getLogger(__name__)

BUILTIN_CFG = {
    "config": None,
    "config_path": "/etc/network/fan",
}


def stop_update_start(distro, service, config_file, content):
    try:
        distro.manage_service("stop", service)
        stop_failed = False
    except subp.ProcessExecutionError as e:
        stop_failed = True
        LOG.warning("failed to stop %s: %s", service, e)

    if not content.endswith("\n"):
        content += "\n"
    util.write_file(config_file, content, omode="w")

    try:
        distro.manage_service("start", service)
        if stop_failed:
            LOG.warning("success: %s started", service)
    except subp.ProcessExecutionError as e:
        LOG.warning("failed to start %s: %s", service, e)

    distro.manage_service("enable", service)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    cfgin = cfg.get("fan")
    if not cfgin:
        cfgin = {}
    mycfg = util.mergemanydict([cfgin, BUILTIN_CFG])

    if not mycfg.get("config"):
        LOG.debug("%s: no 'fan' config entry. disabling", name)
        return

    util.write_file(mycfg.get("config_path"), mycfg.get("config"), omode="w")
    distro = cloud.distro
    if not subp.which("fanctl"):
        distro.install_packages(["ubuntu-fan"])

    stop_update_start(
        distro,
        service="ubuntu-fan",
        config_file=mycfg.get("config_path"),
        content=mycfg.get("config"),
    )
