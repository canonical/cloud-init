# Copyright (c) 2022 Floris Bos
#
# Author: Floris Bos <bos@je-eigen-domein.nl>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""keyboard: set keyboard layout"""

from textwrap import dedent

from cloudinit import distros
from cloudinit import log as logging
from cloudinit.config.schema import (
    MetaSchema,
    get_meta_doc,
    validate_cloudconfig_schema,
)
from cloudinit.settings import PER_INSTANCE

frequency = PER_INSTANCE

# FIXME: setting keyboard layout should be supported by all OSes.
# But currently only implemented for Linux distributions that use systemd.
osfamilies = ["arch", "debian", "redhat", "suse"]
distros = distros.Distro.expand_osfamily(osfamilies)

DEFAULT_KEYBOARD_MODEL = "pc105"

meta: MetaSchema = {
    "id": "cc_keyboard",
    "name": "Keyboard",
    "title": "Set keyboard layout",
    "description": dedent(
        """\
        Handle keyboard configuration.
        """
    ),
    "distros": distros,
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
                        Required. Keyboard layout. Corresponds to XKBLAYOUT.
                        """
                    ),
                },
                "model": {
                    "type": "string",
                    "default": DEFAULT_KEYBOARD_MODEL,
                    "description": dedent(
                        """\
                        Optional. Keyboard model. Corresponds to XKBMODEL.
                        """
                    ),
                },
                "variant": {
                    "type": "string",
                    "description": dedent(
                        """\
                        Optional. Keyboard variant. Corresponds to XKBVARIANT.
                        """
                    ),
                },
                "options": {
                    "type": "string",
                    "description": dedent(
                        """\
                        Optional. Keyboard options. Corresponds to XKBOPTIONS.
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
