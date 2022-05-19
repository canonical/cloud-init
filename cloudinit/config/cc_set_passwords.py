# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Set Passwords: Set user passwords and enable/disable SSH password auth"""

import re
from string import ascii_letters, digits
from textwrap import dedent

from cloudinit import log as logging
from cloudinit import subp, util
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
``list`` and ``expire``. The ``list`` key is used to assign a password to a
to a corresponding pre-existing user. The ``expire`` key is used to set
whether to expire all user passwords such that a password will need to be reset
on the user's next login.

``password`` config key is used to set the default user's password. It is
ignored if the ``chpasswd`` ``list`` is used.
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
            # Set the password for user2 to be a randomly generated password,
            #   which will be written to the system console
            # Set the password for user3 to a pre-hashed password
            ssh_pwauth: false
            chpasswd:
              expire: false
              list:
                - user1:password1
                - user2:RANDOM
                - user3:$6$rounds=4096$5DJ8a9WMTEzIo5J4$Yms6imfeBvf3Yfu84mQBerh18l7OR1Wm1BJXZqFSpJ6BVas0AYJqIjP7czkOaAZHZi1kxQ5Y1IhgWN8K9NgxR1
            """  # noqa
        ),
    ],
}

__doc__ = get_meta_doc(meta)

LOG = logging.getLogger(__name__)

# We are removing certain 'painful' letters/numbers
PW_SET = "".join([x for x in ascii_letters + digits if x not in "loLOI01"])


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
        bmsg = "Leaving SSH config '%s' unchanged." % cfg_name
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


def handle(_name, cfg, cloud, log, args):
    if args:
        # if run from command line, and give args, wipe the chpasswd['list']
        password = args[0]
        if "chpasswd" in cfg and "list" in cfg["chpasswd"]:
            del cfg["chpasswd"]["list"]
    else:
        password = util.get_cfg_option_str(cfg, "password", None)

    expire = True
    plist = None

    if "chpasswd" in cfg:
        chfg = cfg["chpasswd"]
        if "list" in chfg and chfg["list"]:
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
                plist = util.get_cfg_option_str(chfg, "list", plist)
                if plist:
                    plist = plist.splitlines()

        expire = util.get_cfg_option_bool(chfg, "expire", expire)

    if not plist and password:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        if user:
            plist = ["%s:%s" % (user, password)]
        else:
            log.warning("No default or defined user to change password for.")

    errors = []
    if plist:
        plist_in = []
        hashed_plist_in = []
        hashed_users = []
        randlist = []
        users = []
        # N.B. This regex is included in the documentation (i.e. the module
        # docstring), so any changes to it should be reflected there.
        prog = re.compile(r"\$(1|2a|2y|5|6)(\$.+){2}")
        for line in plist:
            u, p = line.split(":", 1)
            if prog.match(p) is not None and ":" not in p:
                hashed_plist_in.append(line)
                hashed_users.append(u)
            else:
                # in this else branch, we potentially change the password
                # hence, a deviation from .append(line)
                if p == "R" or p == "RANDOM":
                    p = rand_user_password()
                    randlist.append("%s:%s" % (u, p))
                plist_in.append("%s:%s" % (u, p))
                users.append(u)
        ch_in = "\n".join(plist_in) + "\n"
        if users:
            try:
                log.debug("Changing password for %s:", users)
                chpasswd(cloud.distro, ch_in)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    log, "Failed to set passwords with chpasswd for %s", users
                )

        hashed_ch_in = "\n".join(hashed_plist_in) + "\n"
        if hashed_users:
            try:
                log.debug("Setting hashed password for %s:", hashed_users)
                chpasswd(cloud.distro, hashed_ch_in, hashed=True)
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
            expired_users = []
            for u in users:
                try:
                    cloud.distro.expire_passwd(u)
                    expired_users.append(u)
                except Exception as e:
                    errors.append(e)
                    util.logexc(log, "Failed to set 'expire' for %s", u)
            if expired_users:
                log.debug("Expired passwords for: %s users", expired_users)

    handle_ssh_pwauth(cfg.get("ssh_pwauth"), cloud.distro)

    if len(errors):
        log.debug("%s errors occurred, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=20):
    return util.rand_str(pwlen, select_from=PW_SET)


def chpasswd(distro, plist_in, hashed=False):
    if util.is_BSD():
        for pentry in plist_in.splitlines():
            u, p = pentry.split(":")
            distro.set_passwd(u, p, hashed=hashed)
    else:
        cmd = ["chpasswd"] + (["-e"] if hashed else [])
        subp.subp(cmd, plist_in)


# vi: ts=4 expandtab
