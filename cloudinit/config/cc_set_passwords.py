# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Set Passwords: Set user passwords and enable/disable SSH password auth"""

import re
from logging import Logger
from string import ascii_letters, digits
from textwrap import dedent
from typing import List

from cloudinit import features
from cloudinit import log as logging
from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.distros import ALL_DISTROS, Distro, ug_util
from cloudinit.settings import PER_INSTANCE
from cloudinit.ssh_util import update_ssh_config

MODULE_DESCRIPTION = """\
This module consumes three top-level config keys: ``ssh_pwauth``, ``chpasswd``
and ``password``.

The ``ssh_pwauth`` config key determines whether or not sshd will be configured
to accept password authentication.

The ``chpasswd`` config key accepts a dictionary containing either or both of
``users`` and ``expire``. The ``users`` key is used to assign a password to a
corresponding pre-existing user. The ``expire`` key is used to set
whether to expire all user passwords specified by this module,
such that a password will need to be reset on the user's next login.

.. note::
    Prior to cloud-init 22.3, the ``expire`` key only applies to plain text
    (including ``RANDOM``) passwords. Post 22.3, the ``expire`` key applies to
    both plain text and hashed passwords.

``password`` config key is used to set the default user's password. It is
ignored if the ``chpasswd`` ``users`` is used. Note: the ``list`` keyword is
deprecated in favor of ``users``.
"""

meta: MetaSchema = {
    "id": "cc_set_passwords",
    "name": "Set Passwords",
    "title": "Set user passwords and enable/disable SSH password auth",
    "description": MODULE_DESCRIPTION,
    "distros": [ALL_DISTROS],
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            # Set a default password that would need to be changed
            # at first login
            ssh_pwauth: true
            password: password1
            """
        ),
        dedent(
            """\
            # Disable ssh password authentication
            # Don't require users to change their passwords on next login
            # Set the password for user1 to be 'password1' (OS does hashing)
            # Set the password for user2 to a pre-hashed password
            # Set the password for user3 to be a randomly generated password,
            #   which will be written to the system console
            ssh_pwauth: false
            chpasswd:
              expire: false
              users:
                - name: user1
                  password: password1
                  type: text
                - name: user2
                  password: $6$rounds=4096$5DJ8a9WMTEzIo5J4$Yms6imfeBvf3Yfu84mQBerh18l7OR1Wm1BJXZqFSpJ6BVas0AYJqIjP7czkOaAZHZi1kxQ5Y1IhgWN8K9NgxR1
                - name: user3
                  type: RANDOM
            """  # noqa
        ),
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)

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


def handle_ssh_pwauth(pw_auth, distro: Distro):
    """Apply sshd PasswordAuthentication changes.

    @param pw_auth: config setting from 'pw_auth'.
                    Best given as True, False, or "unchanged".
    @param distro: an instance of the distro class for the target distribution

    @return: None"""
    service = distro.get_option("ssh_svcname", "ssh")
    restart_ssh = True
    try:
        distro.manage_service("status", service)
    except subp.ProcessExecutionError as e:
        uses_systemd = distro.uses_systemd()
        if not uses_systemd:
            LOG.debug(
                "Writing config 'ssh_pwauth: %s'. SSH service '%s'"
                " will not be restarted because it is not running or not"
                " available.",
                pw_auth,
                service,
            )
            restart_ssh = False
        elif e.exit_code == 3:
            # Service is not running. Write ssh config.
            LOG.debug(
                "Writing config 'ssh_pwauth: %s'. SSH service '%s'"
                " will not be restarted because it is stopped.",
                pw_auth,
                service,
            )
            restart_ssh = False
        elif e.exit_code == 4:
            # Service status is unknown
            LOG.warning(
                "Ignoring config 'ssh_pwauth: %s'."
                " SSH service '%s' is not installed.",
                pw_auth,
                service,
            )
            return
        else:
            LOG.warning(
                "Ignoring config 'ssh_pwauth: %s'."
                " SSH service '%s' is not available. Error: %s.",
                pw_auth,
                service,
                e,
            )
            return

    cfg_name = "PasswordAuthentication"

    if isinstance(pw_auth, str):
        LOG.warning(
            "DEPRECATION: The 'ssh_pwauth' config key should be set to "
            "a boolean value. The string format is deprecated and will be "
            "removed in a future version of cloud-init."
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

    if restart_ssh:
        distro.manage_service("restart", service)
        LOG.debug("Restarted the SSH daemon.")
    else:
        LOG.debug("Not restarting SSH service: service is stopped.")


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:
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
            log.warning(
                "DEPRECATION: key 'lists' is now deprecated. Use 'users'."
            )
            if isinstance(chfg["list"], list):
                log.debug("Handling input for chpasswd as list.")
                plist = util.get_cfg_option_list(chfg, "list", plist)
            else:
                log.warning(
                    "DEPRECATION: The chpasswd multiline string format is "
                    "deprecated and will be removed from a future version of "
                    "cloud-init. Use the list format instead."
                )
                log.debug("Handling input for chpasswd as multiline string.")
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
            log.warning("No default or defined user to change password for.")

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
                log.debug("Changing password for %s:", users)
                distro.chpasswd(plist_in, hashed=False)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    log, "Failed to set passwords with chpasswd for %s", users
                )

        if hashed_users:
            try:
                log.debug("Setting hashed password for %s:", hashed_users)
                distro.chpasswd(hashed_plist_in, hashed=True)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    log,
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
                    util.logexc(log, "Failed to set 'expire' for %s", u)
            if expired_users:
                log.debug("Expired passwords for: %s users", expired_users)

    handle_ssh_pwauth(cfg.get("ssh_pwauth"), distro)

    if len(errors):
        log.debug("%s errors occurred, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=20):
    return util.rand_str(pwlen, select_from=PW_SET)
