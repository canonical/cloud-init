# Copyright (C) 2024, Raspberry Pi Ltd.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import subp
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.settings import PER_INSTANCE
import logging


LOG = logging.getLogger(__name__)
ENABLE_RPI_CONNECT_KEY = "enable_rpi_connect"

meta: MetaSchema = {
    "id": "cc_rpi_connect",
    "distros": ["raspberry-pi-os"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [ENABLE_RPI_CONNECT_KEY],
}


def configure_rpi_connect(enable: bool) -> None:
    LOG.debug("Configuring rpi-connect: %s", enable)

    num = 0 if enable else 1

    try:
        subp.subp(["/usr/bin/raspi-config", "do_rpi_connect", str(num)])
    except subp.ProcessExecutionError as e:
        LOG.error("Failed to configure rpi-connect: %s", e)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if ENABLE_RPI_CONNECT_KEY in cfg:
        # expect it to be a dictionary
        enable = cfg[ENABLE_RPI_CONNECT_KEY]

        if isinstance(enable, bool):
            configure_rpi_connect(enable)
        else:
            LOG.warning(
                "Invalid value for %s: %s", ENABLE_RPI_CONNECT_KEY, enable
            )
