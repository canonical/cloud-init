# Copyright (C) 2024 Raspberry Pi Ltd. All rights reserved.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import shutil

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
            self.log.error("Failed to setup user:", e)
            return False

        # Alacarte fixes
        try:
            # Ensure the sudoers directory exists
            os.makedirs(
                f"/home/{name}/.local/share/applications", exist_ok=True
            )
            os.makedirs(
                f"/home/{name}/.local/share/desktop-directories", exist_ok=True
            )

            stat_info = os.stat(f"/home/{name}")
            uid = stat_info.st_uid
            gid = stat_info.st_gid

            paths = [
                f"/home/{name}/.local",
                f"/home/{name}/.local/share",
                f"/home/{name}/.local/share/applications",
                f"/home/{name}/.local/share/desktop-directories",
            ]

            for path in paths:
                shutil.chown(path, user=uid, group=gid)
                os.chmod(path, 0o755)

        except Exception as e:
            self.log.error("Failed to setup userhome:", e)
            return False

        return True
