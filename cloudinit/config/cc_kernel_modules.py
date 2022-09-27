# This file is part of cloud-init. See LICENSE file for license information.

"""Kernel Modules"""
from logging import Logger
from textwrap import dedent

from cloudinit import log as logging
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

MODULE_DESCRIPTION = dedent(
    """\
"""
)

meta: MetaSchema = {
    "id": "cc_kernel_modules",
    "name": "Kernel Modules",
    "title": "Module to load/blacklist/enhance kernel modules",
    "description": MODULE_DESCRIPTION,
    "distros": ["ubuntu"],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["kernel_modules"],
    "examples": [
        dedent(
            """\
    kernel_modules:
      - name: wireguard
        load: true
      - name: v4l2loopback
        load: true
        modprobe:
          options: "devices=1 video_nr=20 card_label=fakecam exclusive_caps=1"
      - name: zfs
        modprobe:
          blacklist: true
    """
        ),
    ],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    log.debug(f"Hi from module {name}")
