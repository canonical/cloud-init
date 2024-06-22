# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import functools
import logging
import os
import platform
from typing import Any

import cloudinit.distros.bsd
from cloudinit import subp, util

try:
    import crypt  # pylint: disable=W4901

    salt = crypt.METHOD_BLOWFISH  # pylint: disable=E1101
    blowfish_hash: Any = functools.partial(
        crypt.crypt,
        salt=crypt.mksalt(salt),
    )
except (ImportError, AttributeError):
    try:
        from passlib.hash import bcrypt

        blowfish_hash = bcrypt.hash
    except ImportError:

        def blowfish_hash(_):
            """Raise when called so that importing this module doesn't throw
            ImportError when this module is not used. In this case, crypt
            and passlib are not needed.
            """
            raise ImportError(
                "crypt and passlib not found, missing dependency"
            )


LOG = logging.getLogger(__name__)


class NetBSD(cloudinit.distros.bsd.BSD):
    """
    Distro subclass for NetBSD.

    (N.B. OpenBSD inherits from this class.)
    """

    ci_sudoers_fn = "/usr/pkg/etc/sudoers.d/90-cloud-init-users"
    group_add_cmd_prefix = ["groupadd"]

    def __init__(self, name, cfg, paths):
        super().__init__(name, cfg, paths)
        if os.path.exists("/usr/pkg/bin/pkgin"):
            self.pkg_cmd_install_prefix = ["pkgin", "-y", "install"]
            self.pkg_cmd_remove_prefix = ["pkgin", "-y", "remove"]
            self.pkg_cmd_update_prefix = ["pkgin", "-y", "update"]
            self.pkg_cmd_upgrade_prefix = ["pkgin", "-y", "full-upgrade"]
        else:
            self.pkg_cmd_install_prefix = ["pkg_add", "-U"]
            self.pkg_cmd_remove_prefix = ["pkg_delete"]

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        return ["usermod", "-G", group_name, member_name]

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return False

        adduser_cmd = ["useradd"]
        log_adduser_cmd = ["useradd"]

        adduser_opts = {
            "homedir": "-d",
            "gecos": "-c",
            "primary_group": "-g",
            "groups": "-G",
            "shell": "-s",
        }
        adduser_flags = {
            "no_user_group": "--no-user-group",
            "system": "--system",
            "no_log_init": "--no-log-init",
        }

        for key, val in kwargs.items():
            if key in adduser_opts and val and isinstance(val, str):
                adduser_cmd.extend([adduser_opts[key], val])

            elif key in adduser_flags and val:
                adduser_cmd.append(adduser_flags[key])
                log_adduser_cmd.append(adduser_flags[key])

        if "no_create_home" not in kwargs or "system" not in kwargs:
            adduser_cmd += ["-m"]
            log_adduser_cmd += ["-m"]

        adduser_cmd += [name]
        log_adduser_cmd += [name]

        # Run the command
        LOG.info("Adding user %s", name)
        try:
            subp.subp(adduser_cmd, logstring=log_adduser_cmd)
        except Exception:
            util.logexc(LOG, "Failed to create user %s", name)
            raise
        # Set the password if it is provided
        # For security consideration, only hashed passwd is assumed
        passwd_val = kwargs.get("passwd", None)
        if passwd_val is not None:
            self.set_passwd(name, passwd_val, hashed=True)

    def set_passwd(self, user, passwd, hashed=False):
        if hashed:
            hashed_pw = passwd
        else:
            hashed_pw = blowfish_hash(passwd)

        try:
            subp.subp(["usermod", "-p", hashed_pw, user])
        except Exception:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise
        self.unlock_passwd(user)

    def lock_passwd(self, name):
        try:
            subp.subp(["usermod", "-C", "yes", name])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def unlock_passwd(self, name):
        try:
            subp.subp(["usermod", "-C", "no", name])
        except Exception:
            util.logexc(LOG, "Failed to unlock user %s", name)
            raise

    def apply_locale(self, locale, out_fn=None):
        LOG.debug("Cannot set the locale.")

    def _get_pkg_cmd_environ(self):
        """Return env vars used in NetBSD package_command operations"""
        os_release = platform.release()
        os_arch = platform.machine()
        return {
            "PKG_PATH": (
                f"http://cdn.netbsd.org/pub/pkgsrc/packages/NetBSD"
                f"/{os_arch}/{os_release}/All"
            )
        }

    def update_package_sources(self, *, force=False):
        pass


class Distro(NetBSD):
    pass
