# Copyright (C) 2024-2025 Raspberry Pi Ltd. All rights reserved.
#
# Author: Paul Oberosler <paul.oberosler@raspberrypi.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os

from cloudinit import net, subp, util
from cloudinit.distros import debian

LOG = logging.getLogger(__name__)


class Distro(debian.Distro):
    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        self.default_user_renamed = False

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
        Add a user to the system using standard Raspberry Pi tools

        Returns False if user already exists, otherwise True.
        """
        if self.default_user_renamed:
            return super().add_user(name, **kwargs)

        self.default_user_renamed = True

        # Password precedence: hashed > passwd (legacy hash) > plaintext
        pw_hash = kwargs.get("hashed_passwd") or kwargs.get("passwd")
        plain = kwargs.get("plain_text_passwd")

        if pw_hash:
            subp.subp(
                ["/usr/lib/userconf-pi/userconf", name, pw_hash],
            )
        else:
            subp.subp(
                [
                    "/usr/lib/userconf-pi/userconf",
                    name,
                ],
            )
            if plain:
                self.set_passwd(name, plain, hashed=False)

        # Mask userconfig.service to ensure it does not start the
        # first-run setup wizard on Raspberry Pi OS Lite images.
        # The 'systemctl disable' call performed by the userconf tool
        # only takes effect after a reboot, so masking it ensures the
        # service stays inactive immediately.
        #
        # On desktop images, userconf alone is sufficient to prevent
        # the graphical first-run wizard, but masking the service here
        # adds consistency and causes no harm.
        self.manage_service("mask", "userconfig.service", "--now")

        # Continue handling any remaining options
        # that the base add_user() implementation would normally process.

        # Ensure groups exist if requested
        create_groups = kwargs.get("create_groups", True)
        groups = kwargs.get("groups")
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",")]
        if create_groups and groups:
            for g in groups:
                if not util.is_group(g):
                    self.create_group(g)

        # apply creation-time attributes post-rename
        if kwargs.get("gecos"):
            subp.subp(["usermod", "-c", kwargs["gecos"], name])
        if kwargs.get("shell"):
            subp.subp(["usermod", "-s", kwargs["shell"], name])
        if kwargs.get("primary_group"):
            pg = kwargs["primary_group"]
            if create_groups and not util.is_group(pg):
                self.create_group(pg)
            subp.subp(["usermod", "-g", pg, name])
        if groups:
            subp.subp(["usermod", "-G", ",".join(groups), name])
        if kwargs.get("expiredate"):
            subp.subp(["usermod", "--expiredate", kwargs["expiredate"], name])
        if kwargs.get("inactive"):
            subp.subp(["usermod", "--inactive", str(kwargs["inactive"]), name])
        if kwargs.get("uid") is not None:
            new_uid = int(kwargs["uid"])
            subp.subp(["usermod", "-u", str(new_uid), name])

            # Also adjust ownership of the homedir if it exists
            homedir = kwargs.get("homedir") or f"/home/{name}"
            if os.path.exists(homedir):
                for root, dirs, files in os.walk(homedir):
                    for d in dirs:
                        util.chownbyid(
                            os.path.join(root, d), uid=new_uid, gid=-1
                        )
                    for f in files:
                        util.chownbyid(
                            os.path.join(root, f), uid=new_uid, gid=-1
                        )
                util.chownbyid(homedir, uid=new_uid, gid=-1)
        if kwargs.get("homedir"):
            subp.subp(["usermod", "-d", kwargs["homedir"], "-m", name])

        # `create_user` will still run post-creation bits:
        # hashed/plain_text passwd (already set above, ok if redundant),
        # lock_passwd, sudo, doas, ssh_authorized_keys, ssh_redirect_user
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
