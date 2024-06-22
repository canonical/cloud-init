# Copyright (C) 2014 Harm Weites
#
# Author: Harm Weites <harm@weites.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import logging
import os
import re
from io import StringIO

import cloudinit.distros.bsd
from cloudinit import subp, util
from cloudinit.distros.networking import FreeBSDNetworking
from cloudinit.settings import PER_ALWAYS, PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(cloudinit.distros.bsd.BSD):
    """
    Distro subclass for FreeBSD.

    (N.B. DragonFlyBSD inherits from this class.)
    """

    networking_cls = FreeBSDNetworking
    usr_lib_exec = "/usr/local/lib"
    login_conf_fn = "/etc/login.conf"
    login_conf_fn_bak = "/etc/login.conf.orig"
    ci_sudoers_fn = "/usr/local/etc/sudoers.d/90-cloud-init-users"
    group_add_cmd_prefix = ["pw", "group", "add"]
    pkg_cmd_install_prefix = ["pkg", "install"]
    pkg_cmd_remove_prefix = ["pkg", "remove"]
    pkg_cmd_update_prefix = ["pkg", "update"]
    pkg_cmd_upgrade_prefix = ["pkg", "upgrade"]
    prefer_fqdn = True  # See rc.conf(5) in FreeBSD
    home_dir = "/usr/home"
    # FreeBSD has the following dhclient lease path:
    # /var/db/dhclient.leases.<iface_name>
    dhclient_lease_directory = "/var/db"
    dhclient_lease_file_regex = r"dhclient.leases.\w+"

    @classmethod
    def reload_init(cls, rcs=None):
        """
        Tell rc to reload its configuration
        Note that this only works while we're still in the process of booting.
        May raise ProcessExecutionError
        """
        rc_pid = os.environ.get("RC_PID")
        if rc_pid is None:
            LOG.warning("Unable to reload rc(8): no RC_PID in Environment")
            return

        return subp.subp(["kill", "-SIGALRM", rc_pid], capture=True, rcs=rcs)

    @classmethod
    def manage_service(
        cls, action: str, service: str, *extra_args: str, rcs=None
    ):
        """
        Perform the requested action on a service. This handles FreeBSD's
        'service' case. The FreeBSD 'service' is closer in features to
        'systemctl' than SysV init's 'service', so we override it.
        May raise ProcessExecutionError
        """
        init_cmd = cls.init_cmd
        cmds = {
            "stop": [service, "stop"],
            "start": [service, "start"],
            "enable": [service, "enable"],
            "enabled": [service, "enabled"],
            "disable": [service, "disable"],
            "onestart": [service, "onestart"],
            "onestop": [service, "onestop"],
            "restart": [service, "restart"],
            "reload": [service, "restart"],
            "try-reload": [service, "restart"],
            "status": [service, "status"],
            "onestatus": [service, "onestatus"],
        }
        cmd = init_cmd + cmds[action] + list(extra_args)
        return subp.subp(cmd, capture=True, rcs=rcs)

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        return ["pw", "usermod", "-n", member_name, "-G", group_name]

    def add_user(self, name, **kwargs):
        if util.is_user(name):
            LOG.info("User %s already exists, skipping.", name)
            return False

        pw_useradd_cmd = ["pw", "useradd", "-n", name]
        log_pw_useradd_cmd = ["pw", "useradd", "-n", name]

        pw_useradd_opts = {
            "homedir": "-d",
            "gecos": "-c",
            "primary_group": "-g",
            "groups": "-G",
            "shell": "-s",
            "inactive": "-E",
            "uid": "-u",
        }
        pw_useradd_flags = {
            "no_user_group": "--no-user-group",
            "system": "--system",
            "no_log_init": "--no-log-init",
        }

        for key, val in kwargs.items():
            if key in pw_useradd_opts and val and isinstance(val, (str, int)):
                pw_useradd_cmd.extend([pw_useradd_opts[key], str(val)])

            elif key in pw_useradd_flags and val:
                pw_useradd_cmd.append(pw_useradd_flags[key])
                log_pw_useradd_cmd.append(pw_useradd_flags[key])

        if "no_create_home" in kwargs or "system" in kwargs:
            pw_useradd_cmd.append("-d/nonexistent")
            log_pw_useradd_cmd.append("-d/nonexistent")
        else:
            homedir = kwargs.get("homedir", f"{self.home_dir}/{name}")
            pw_useradd_cmd.append("-d" + homedir)
            pw_useradd_cmd.append("-m")
            log_pw_useradd_cmd.append("-d" + homedir)
            log_pw_useradd_cmd.append("-m")

        # Run the command
        LOG.info("Adding user %s", name)
        try:
            subp.subp(pw_useradd_cmd, logstring=log_pw_useradd_cmd)
        except Exception:
            util.logexc(LOG, "Failed to create user %s", name)
            raise
        # Set the password if it is provided
        # For security consideration, only hashed passwd is assumed
        passwd_val = kwargs.get("passwd", None)
        if passwd_val is not None:
            self.set_passwd(name, passwd_val, hashed=True)

    def expire_passwd(self, user):
        try:
            subp.subp(["pw", "usermod", user, "-p", "01-Jan-1970"])
        except Exception:
            util.logexc(LOG, "Failed to set pw expiration for %s", user)
            raise

    def set_passwd(self, user, passwd, hashed=False):
        if hashed:
            hash_opt = "-H"
        else:
            hash_opt = "-h"

        try:
            subp.subp(
                ["pw", "usermod", user, hash_opt, "0"],
                data=passwd,
                logstring="chpasswd for %s" % user,
            )
        except Exception:
            util.logexc(LOG, "Failed to set password for %s", user)
            raise

    def lock_passwd(self, name):
        try:
            subp.subp(["pw", "usermod", name, "-w", "no"])
        except Exception:
            util.logexc(LOG, "Failed to lock password login for user %s", name)
            raise

    def apply_locale(self, locale, out_fn=None):
        # Adjust the locales value to the new value
        newconf = StringIO()
        for line in util.load_text_file(self.login_conf_fn).splitlines():
            newconf.write(
                re.sub(r"^default:", r"default:lang=%s:" % locale, line)
            )
            newconf.write("\n")

        # Make a backup of login.conf.
        util.copy(self.login_conf_fn, self.login_conf_fn_bak)

        # And write the new login.conf.
        util.write_file(self.login_conf_fn, newconf.getvalue())

        try:
            LOG.debug("Running cap_mkdb for %s", locale)
            subp.subp(["cap_mkdb", self.login_conf_fn])
        except subp.ProcessExecutionError:
            # cap_mkdb failed, so restore the backup.
            util.logexc(LOG, "Failed to apply locale %s", locale)
            try:
                util.copy(self.login_conf_fn_bak, self.login_conf_fn)
            except IOError:
                util.logexc(
                    LOG, "Failed to restore %s backup", self.login_conf_fn
                )

    def _get_pkg_cmd_environ(self):
        """Return environment vars used in FreeBSD package_command
        operations"""
        return {"ASSUME_ALWAYS_YES": "YES"}

    def update_package_sources(self, *, force=False):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["update"],
            freq=PER_ALWAYS if force else PER_INSTANCE,
        )

    @staticmethod
    def build_dhclient_cmd(
        path: str,
        lease_file: str,
        pid_file: str,
        interface: str,
        config_file: str,
    ) -> list:
        return [path, "-l", lease_file, "-p", pid_file] + (
            ["-c", config_file, interface] if config_file else [interface]
        )

    @staticmethod
    def eject_media(device: str) -> None:
        subp.subp(["camcontrol", "eject", device])
