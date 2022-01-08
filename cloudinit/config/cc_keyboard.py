# Copyright (c) 2022 Floris Bos
#
# Author: Floris Bos <bos@je-eigen-domein.nl>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""keyboard: set keyboard layout"""

from textwrap import dedent

from cloudinit import distros
from cloudinit import log as logging
from cloudinit.config.schema import get_meta_doc, validate_cloudconfig_schema
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

# FIXME: setting keyboard layout should be suppored by all OSes.
# But currently only implemented for Linux distributions that use systemd.
osfamilies = ["arch", "debian", "redhat", "suse"]
distros = distros.Distro.expand_osfamily(osfamilies)

DEFAULT_KEYBOARD_MODEL = "pc105"

meta = {
    "id": "cc_keyboard",
    "name": "Keyboard",
    "title": "set keyboard layout",
    "description": dedent(
        """\
        Handle keyboard configuration.
        """
    ),
    "distros": distros,
    "examples": [
        dedent(
            """\
            keyboard:
              layout: us
            """
        ),
        dedent(
            """\
            keyboard:
              layout: de
              model: pc105
              variant: nodeadkeys
              options: compose:rwin
            """
        ),
    ],
    "frequency": frequency,
}


schema = {
    "type": "object",
    "properties": {
        "keyboard": {
            "type": "object",
            "properties": {
                "layout": {
                    "type": "string",
                    "description": dedent(
                        """\
                        Keyboard layout. Corresponds to XKBLAYOUT.
                        """
                    ),
                },
                "model": {
                    "type": "string",
                    "default": DEFAULT_KEYBOARD_MODEL,
                    "description": dedent(
                        """\
                        Keyboard model. Corresponds to XKBMODEL.
                        """
                    ),
                },
                "variant": {
                    "type": "string",
                    "description": dedent(
                        """\
                        Keyboard variant. Corresponds to XKBVARIANT.
                        """
                    ),
                },
                "options": {
                    "type": "string",
                    "description": dedent(
                        """\
                        Keyboard options. Corresponds to XKBOPTIONS.
                        """
                    ),
                },
            },
            "required": ["layout"],
            "additionalProperties": False,
        }
    },
}

__doc__ = get_meta_doc(meta, schema)

LOG = logging.getLogger(__name__)


def handle(name, cfg, cloud, log, args):
    if "keyboard" not in cfg:
        LOG.debug(
            "Skipping module named %s, no 'keyboard' section found", name
        )
        return
    validate_cloudconfig_schema(cfg, schema)
    kb_cfg = cfg["keyboard"]
    layout = kb_cfg["layout"]
    model = kb_cfg.get("model", DEFAULT_KEYBOARD_MODEL)
    variant = kb_cfg.get("variant", "")
    options = kb_cfg.get("options", "")
    LOG.debug("Setting keyboard layout to '%s'", layout)
    cloud.distro.set_keymap(layout, model, variant, options)


# vi: ts=4 expandtab
