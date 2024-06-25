# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Set Passwords: Set user passwords and enable/disable SSH password auth"""

import logging
import re
from string import ascii_letters, digits
from typing import List

from cloudinit import features, subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema
from cloudinit.distros import ALL_DISTROS, Distro, ug_util
from cloudinit.settings import PER_INSTANCE
from cloudinit.ssh_util import update_ssh_config

meta: MetaSchema = {
    "id": "cc_set_passwords",
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "activate_by_schema_keys": [],
}  # type: ignore

LOG = logging.getLogger(__name__)

# We are removing certain 'painful' letters/numbers
PW_SET = "".join([x for x in ascii_letters + digits if x not in "loLOI01"])


def get_users_by_type(users_list: list, pw_type: str) -> list:
    """either password or type: RANDOM is required, user is always required"""
    return (
        []
        if not users_list
        else [
            (item["name"], item.get("password", "RANDOM"))
            for item in users_list
            if item.get("type", "hash") == pw_type
        ]
    )


def _restart_ssh_daemon(distro, service):
    try:
        distro.manage_service("restart", service)
        LOG.debug("Restarted the SSH daemon.")
    except subp.ProcessExecutionError as e:
        LOG.warning(
            "'ssh_pwauth' configuration may not be applied. Cloud-init was "
            "unable to restart SSH daemon due to error: '%s'",
            e,
        )


def handle_ssh_pwauth(pw_auth, distro: Distro):
    """Apply sshd PasswordAuthentication changes.

    @param pw_auth: config setting from 'pw_auth'.
                    Best given as True, False, or "unchanged".
    @param distro: an instance of the distro class for the target distribution

    @return: None"""
    service = distro.get_option("ssh_svcname", "ssh")

    cfg_name = "PasswordAuthentication"

    if isinstance(pw_auth, str):
        util.deprecate(
            deprecated="Using a string value for the 'ssh_pwauth' key",
            deprecated_version="22.2",
            extra_message="Use a boolean value with 'ssh_pwauth'.",
        )
    if util.is_true(pw_auth):
        cfg_val = "yes"
    elif util.is_false(pw_auth):
        cfg_val = "no"
    else:
        bmsg = f"Leaving SSH config '{cfg_name}' unchanged."
        if pw_auth is None or pw_auth.lower() == "unchanged":
            LOG.debug("%s ssh_pwauth=%s", bmsg, pw_auth)
        else:
            LOG.warning("%s Unrecognized value: ssh_pwauth=%s", bmsg, pw_auth)
        return

    updated = update_ssh_config({cfg_name: cfg_val})
    if not updated:
        LOG.debug("No need to restart SSH service, %s not updated.", cfg_name)
        return

    if distro.uses_systemd():
        state = subp.subp(
            [
                "systemctl",
                "show",
                "--property",
                "ActiveState",
                "--value",
                service,
            ]
        ).stdout.strip()
        if state.lower() in ["active", "activating", "reloading"]:
            _restart_ssh_daemon(distro, service)
    else:
        _restart_ssh_daemon(distro, service)


def handle(name: str, cfg: Config, cloud: Cloud, args: list) -> None:
    distro: Distro = cloud.distro
    if args:
        # if run from command line, and give args, wipe the chpasswd['list']
        password = args[0]
        if "chpasswd" in cfg and "list" in cfg["chpasswd"]:
            del cfg["chpasswd"]["list"]
    else:
        password = util.get_cfg_option_str(cfg, "password", None)

    expire = True
    plist: List = []
    users_list: List = []

    if "chpasswd" in cfg:
        chfg = cfg["chpasswd"]
        users_list = util.get_cfg_option_list(chfg, "users", default=[])
        if "list" in chfg and chfg["list"]:
            util.deprecate(
                deprecated="Config key 'lists'",
                deprecated_version="22.3",
                extra_message="Use 'users' instead.",
            )
            if isinstance(chfg["list"], list):
                LOG.debug("Handling input for chpasswd as list.")
                plist = util.get_cfg_option_list(chfg, "list", plist)
            else:
                util.deprecate(
                    deprecated="The chpasswd multiline string",
                    deprecated_version="22.2",
                    extra_message="Use string type instead.",
                )
                LOG.debug("Handling input for chpasswd as multiline string.")
                multiline = util.get_cfg_option_str(chfg, "list")
                if multiline:
                    plist = multiline.splitlines()

        expire = util.get_cfg_option_bool(chfg, "expire", expire)

    if not (users_list or plist) and password:
        (users, _groups) = ug_util.normalize_users_groups(cfg, distro)
        (user, _user_config) = ug_util.extract_default(users)
        if user:
            plist = ["%s:%s" % (user, password)]
        else:
            LOG.warning("No default or defined user to change password for.")

    errors = []
    if plist or users_list:
        # This section is for parsing the data that arrives in the form of
        #   chpasswd:
        #     users:
        plist_in = get_users_by_type(users_list, "text")
        users = [user for user, _ in plist_in]
        hashed_plist_in = get_users_by_type(users_list, "hash")
        hashed_users = [user for user, _ in hashed_plist_in]
        randlist = []
        for user, _ in get_users_by_type(users_list, "RANDOM"):
            password = rand_user_password()
            users.append(user)
            plist_in.append((user, password))
            randlist.append(f"{user}:{password}")

        # This for loop is for parsing the data that arrives in the deprecated
        # form of
        #   chpasswd:
        #     list:
        # N.B. This regex is included in the documentation (i.e. the schema
        # docstring), so any changes to it should be reflected there.
        prog = re.compile(r"\$(1|2a|2y|5|6)(\$.+){2}")
        for line in plist:
            u, p = line.split(":", 1)
            if prog.match(p) is not None and ":" not in p:
                hashed_plist_in.append((u, p))
                hashed_users.append(u)
            else:
                # in this else branch, we potentially change the password
                # hence, a deviation from .append(line)
                if p == "R" or p == "RANDOM":
                    p = rand_user_password()
                    randlist.append("%s:%s" % (u, p))
                plist_in.append((u, p))
                users.append(u)
        if users:
            try:
                LOG.debug("Changing password for %s:", users)
                distro.chpasswd(plist_in, hashed=False)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    LOG, "Failed to set passwords with chpasswd for %s", users
                )

        if hashed_users:
            try:
                LOG.debug("Setting hashed password for %s:", hashed_users)
                distro.chpasswd(hashed_plist_in, hashed=True)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    LOG,
                    "Failed to set hashed passwords with chpasswd for %s",
                    hashed_users,
                )

        if len(randlist):
            blurb = (
                "Set the following 'random' passwords\n",
                "\n".join(randlist),
            )
            util.multi_log(
                "%s\n%s\n" % blurb, stderr=False, fallback_to_stdout=False
            )

        if expire:
            users_to_expire = users
            if features.EXPIRE_APPLIES_TO_HASHED_USERS:
                users_to_expire += hashed_users
            expired_users = []
            for u in users_to_expire:
                try:
                    distro.expire_passwd(u)
                    expired_users.append(u)
                except Exception as e:
                    errors.append(e)
                    util.logexc(LOG, "Failed to set 'expire' for %s", u)
            if expired_users:
                LOG.debug("Expired passwords for: %s users", expired_users)

    handle_ssh_pwauth(cfg.get("ssh_pwauth"), distro)

    if len(errors):
        LOG.debug("%s errors occurred, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=20):
    return util.rand_str(pwlen, select_from=PW_SET)
