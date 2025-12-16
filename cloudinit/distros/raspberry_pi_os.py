# Copyright (C) 2024-2025 Raspberry Pi Ltd. All rights reserved.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging

from cloudinit import net, subp
from cloudinit.distros import debian

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):
    def set_keymap(self, layout: str, model: str, variant: str, options: str):
        super().set_keymap(layout, model, variant, options)

        subp.subp(
            [
                "/usr/bin/raspi-config",
                "nonint",
                "update_labwc_keyboard",
            ],
        )
        subp.subp(
            [
                "/usr/bin/raspi-config",
                "nonint",
                "update_squeekboard",
                "restart",
            ],
        )
        self.manage_service("restart", "keyboard-setup")

        if subp.which("udevadm"):
            subp.subp(
                [
                    "udevadm",
                    "trigger",
                    "--subsystem-match=input",
                    "--action=change",
                ],
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
                LOG.error("Failed to set locale %s", locale)

    def add_user(self, name, **kwargs) -> bool:
        """
        Add a user to the system using standard GNU tools

        This should be overridden on distros where useradd is not desirable or
        not available.

        Returns False if user already exists, otherwise True.
        """
        result = super().add_user(name, **kwargs)

        if not result:
            return result

        try:
            subp.subp(
                [
                    "/usr/bin/rename-user",
                    "-f",
                    "-s",
                ],
                update_env={"SUDO_USER": name},
            )

        except subp.ProcessExecutionError as e:
            LOG.error("Failed to setup user: %s", e)
            return False

        return True

    def generate_fallback_config(self):
        # Based on Photon OS implementation
        key = "disable_fallback_netcfg"
        disable_fallback_netcfg = self._cfg.get(key, True)
        LOG.debug("%s value is: %s", key, disable_fallback_netcfg)

        if not disable_fallback_netcfg:
            return net.generate_fallback_config()

        LOG.info(
            "Skipping generation of fallback network config as per "
            "configuration. Rely on Raspberry Pi OS's default "
            "network configuration."
        )
        return None
