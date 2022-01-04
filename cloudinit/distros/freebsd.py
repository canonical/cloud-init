# Copyright (C) 2014 Harm Weites
#
# Author: Harm Weites <harm@weites.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import re
from io import StringIO

import cloudinit.distros.bsd
from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.settings import PER_INSTANCE

LOG = logging.getLogger(__name__)


class Distro(cloudinit.distros.bsd.BSD):
    """
    Distro subclass for FreeBSD.

    (N.B. DragonFlyBSD inherits from this class.)
    """

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
        }
        pw_useradd_flags = {
            "no_user_group": "--no-user-group",
            "system": "--system",
            "no_log_init": "--no-log-init",
        }

        for key, val in kwargs.items():
            if key in pw_useradd_opts and val and isinstance(val, str):
                pw_useradd_cmd.extend([pw_useradd_opts[key], val])

            elif key in pw_useradd_flags and val:
                pw_useradd_cmd.append(pw_useradd_flags[key])
                log_pw_useradd_cmd.append(pw_useradd_flags[key])

        if "no_create_home" in kwargs or "system" in kwargs:
            pw_useradd_cmd.append("-d/nonexistent")
            log_pw_useradd_cmd.append("-d/nonexistent")
        else:
            pw_useradd_cmd.append(
                "-d{home_dir}/{name}".format(home_dir=self.home_dir, name=name)
            )
            pw_useradd_cmd.append("-m")
            log_pw_useradd_cmd.append(
                "-d{home_dir}/{name}".format(home_dir=self.home_dir, name=name)
            )

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
            subp.subp(["pw", "usermod", name, "-h", "-"])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def apply_locale(self, locale, out_fn=None):
        # Adjust the locales value to the new value
        newconf = StringIO()
        for line in util.load_file(self.login_conf_fn).splitlines():
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

    def apply_network_config_names(self, netconfig):
        # This is handled by the freebsd network renderer. It writes in
        # /etc/rc.conf a line with the following format:
        #    ifconfig_OLDNAME_name=NEWNAME
        # FreeBSD network script will rename the interface automatically.
        pass

    def _get_pkg_cmd_environ(self):
        """Return environment vars used in *BSD package_command operations"""
        e = os.environ.copy()
        e["ASSUME_ALWAYS_YES"] = "YES"
        return e

    def update_package_sources(self):
        self._runner.run(
            "update-sources",
            self.package_command,
            ["update"],
            freq=PER_INSTANCE,
        )


# vi: ts=4 expandtab
