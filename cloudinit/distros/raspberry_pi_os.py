# Copyright (C) 2024-2025 Raspberry Pi Ltd. All rights reserved.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import subp
from cloudinit.distros import debian

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):
    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        self.default_user_renamed = False

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
            if not locale.endswith(".UTF-8"):
                LOG.info("Trying to set locale %s.UTF-8", locale)
                subp.subp(
                    [
                        "/usr/bin/raspi-config",
                        "nonint",
                        "do_change_locale",
                        f"{locale}.UTF-8",
                    ]
                )
            else:
                LOG.error("Failed to set locale %s")

    def add_user(self, name, **kwargs) -> bool:
        """
        Add a user to the system using standard Raspberry Pi tools

        Returns False if user already exists, otherwise True.
        """
        if self.default_user_renamed:
            return super().add_user(name, **kwargs)
        self.default_user_renamed = True

        try:
            subp.subp(
                [
                    "/usr/lib/userconf-pi/userconf",
                    name,
                ],
            )

        except subp.ProcessExecutionError as e:
            LOG.error("Failed to setup user: %s", e)
            return False

        return True
