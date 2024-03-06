# Copyright (c) 2022 Floris Bos
#
# Author: Floris Bos <bos@je-eigen-domein.nl>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""keyboard: set keyboard layout"""

import logging
from textwrap import dedent

from cloudinit import distros
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

# FIXME: setting keyboard layout should be supported by all OSes.
# But currently only implemented for Linux distributions that use systemd,
# plus Alpine Linux.

DEFAULT_KEYBOARD_MODEL = "pc105"

supported_distros = distros.Distro.expand_osfamily(
    ["alpine", "arch", "debian", "redhat", "suse"]
)

meta: MetaSchema = {
    "id": "cc_keyboard",
    "name": "Keyboard",
    "title": "Set keyboard layout",
    "description": "Handle keyboard configuration.",
    "distros": supported_distros,
    "examples": [
        dedent(
            """\
            # Set keyboard layout to "us"
            keyboard:
              layout: us
            """
        ),
        dedent(
            """\
            # Set specific keyboard layout, model, variant, options
            keyboard:
              layout: de
              model: pc105
              variant: nodeadkeys
              options: compose:rwin
            """
        ),
        dedent(
            """\
            # For Alpine Linux set specific keyboard layout and variant,
            # as used by setup-keymap. Model and options are ignored.
            keyboard:
              layout: gb
              variant: gb-extd
            """
        ),
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["keyboard"],
}


__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    if "keyboard" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'keyboard' section found", name
        )
        return
    kb_cfg = cfg["keyboard"]
    layout = kb_cfg["layout"]
    if cloud.distro.name == "alpine":
        model = kb_cfg.get("model", "")
    else:
        model = kb_cfg.get("model", DEFAULT_KEYBOARD_MODEL)
    variant = kb_cfg.get("variant", "")
    options = kb_cfg.get("options", "")
    LOG.debug("Setting keyboard layout to '%s'", layout)
    cloud.distro.set_keymap(layout, model, variant, options)
