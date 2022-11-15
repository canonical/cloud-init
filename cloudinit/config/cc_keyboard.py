# Copyright (c) 2022 Floris Bos
#
# Author: Floris Bos <bos@je-eigen-domein.nl>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""keyboard: set keyboard layout"""

from logging import Logger
from textwrap import dedent

from cloudinit import distros
from cloudinit import log as logging
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE

# FIXME: setting keyboard layout should be supported by all OSes.
# But currently only implemented for Linux distributions that use systemd.

DEFAULT_KEYBOARD_MODEL = "pc105"

supported_distros = distros.Distro.expand_osfamily(
    ["arch", "debian", "redhat", "suse"]
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
    ],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": ["keyboard"],
}


__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
    if "keyboard" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'keyboard' section found", name
        )
        return
    kb_cfg = cfg["keyboard"]
    layout = kb_cfg["layout"]
    model = kb_cfg.get("model", DEFAULT_KEYBOARD_MODEL)
    variant = kb_cfg.get("variant", "")
    options = kb_cfg.get("options", "")
    LOG.debug("Setting keyboard layout to '%s'", layout)
    cloud.distro.set_keymap(layout, model, variant, options)


# vi: ts=4 expandtab
