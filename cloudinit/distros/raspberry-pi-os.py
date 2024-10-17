# Copyright (C) 2024 Raspberry Pi Ltd. All rights reserved.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

from cloudinit import subp
from cloudinit.distros import debian


class Distro(debian.Distro):
    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)

    def set_keymap(self, layout: str, model: str, variant: str, options: str):
        """Currently Raspberry Pi OS sys-mods only supports
        setting the layout"""

        subp.subp(
            [
                "/usr/lib/raspberrypi-sys-mods/imager_custom",
                "set_keymap",
                layout,
            ]
        )

    def apply_locale(self, locale, out_fn=None, keyname="LANG"):
        try:
            subp.subp(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    "do_change_locale",
                    f"{locale}",
                ]
            )
        except subp.ProcessExecutionError:
            subp.subp(
                [
                    "/usr/bin/raspi-config",
                    "nonint",
                    "do_change_locale",
                    f"{locale}.UTF-8",
                ]
            )
