"""Bootc: Switch to a different bootc image."""

import logging
import os

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS
from cloudinit.settings import PER_INSTANCE

meta: MetaSchema = {
    "id": "cc_bootc",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["bootc"],
}

LOG = logging.getLogger(__name__)

def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    bootc = cfg.get('bootc')
    if not bootc:
        LOG.warning("No 'bootc' configuration found, skipping.")
        return

    image = util.get_cfg_option_str(bootc, "image")
    if not image:
        raise ValueError("No 'image' specified in the 'bootc' configuration.")

    LOG.info(f"Switching to bootc image: {image}")

    try:
        command = ["bootc", "switch", "--apply", image]
        subp.subp(command)
        LOG.info(f"Successfully executed: {' '.join(command)}")
    except subp.CalledProcessError as e:
        LOG.error(f"Command failed with error: {e}")
        raise
