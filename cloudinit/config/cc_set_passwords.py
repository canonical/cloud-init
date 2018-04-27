# Copyright (C) 2009-2010 Canonical Ltd.
# Copyright (C) 2012, 2013 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
#
# This file is part of cloud-init. See LICENSE file for license information.

"""
Set Passwords
-------------
**Summary:** Set user passwords

Set system passwords and enable or disable ssh password authentication.
The ``chpasswd`` config key accepts a dictionary containing a single one of two
keys, either ``expire`` or ``list``. If ``expire`` is specified and is set to
``false``, then the ``password`` global config key is used as the password for
all user accounts. If the ``expire`` key is specified and is set to ``true``
then user passwords will be expired, preventing the default system passwords
from being used.

If the ``list`` key is provided, a list of
``username:password`` pairs can be specified. The usernames specified
must already exist on the system, or have been created using the
``cc_users_groups`` module. A password can be randomly generated using
``username:RANDOM`` or ``username:R``. A hashed password can be specified
using ``username:$6$salt$hash``. Password ssh authentication can be
enabled, disabled, or left to system defaults using ``ssh_pwauth``.

.. note::
    if using ``expire: true`` then a ssh authkey should be specified or it may
    not be possible to login to the system

**Internal name:** ``cc_set_passwords``

**Module frequency:** per instance

**Supported distros:** all

**Config keys**::

    ssh_pwauth: <yes/no/unchanged>

    password: password1
    chpasswd:
        expire: <true/false>

    chpasswd:
        list: |
            user1:password1
            user2:RANDOM
            user3:password3
            user4:R

    ##
    # or as yaml list
    ##
    chpasswd:
        list:
            - user1:password1
            - user2:RANDOM
            - user3:password3
            - user4:R
            - user4:$6$rL..$ej...
"""

import re
import sys

from cloudinit.distros import ug_util
from cloudinit import log as logging
from cloudinit.ssh_util import update_ssh_config
from cloudinit import util

from string import ascii_letters, digits

LOG = logging.getLogger(__name__)

# We are removing certain 'painful' letters/numbers
PW_SET = (''.join([x for x in ascii_letters + digits
                   if x not in 'loLOI01']))


def handle_ssh_pwauth(pw_auth, service_cmd=None, service_name="ssh"):
    """Apply sshd PasswordAuthentication changes.

    @param pw_auth: config setting from 'pw_auth'.
                    Best given as True, False, or "unchanged".
    @param service_cmd: The service command list (['service'])
    @param service_name: The name of the sshd service for the system.

    @return: None"""
    cfg_name = "PasswordAuthentication"
    if service_cmd is None:
        service_cmd = ["service"]

    if util.is_true(pw_auth):
        cfg_val = 'yes'
    elif util.is_false(pw_auth):
        cfg_val = 'no'
    else:
        bmsg = "Leaving ssh config '%s' unchanged." % cfg_name
        if pw_auth is None or pw_auth.lower() == 'unchanged':
            LOG.debug("%s ssh_pwauth=%s", bmsg, pw_auth)
        else:
            LOG.warning("%s Unrecognized value: ssh_pwauth=%s", bmsg, pw_auth)
        return

    updated = update_ssh_config({cfg_name: cfg_val})
    if not updated:
        LOG.debug("No need to restart ssh service, %s not updated.", cfg_name)
        return

    if 'systemctl' in service_cmd:
        cmd = list(service_cmd) + ["restart", service_name]
    else:
        cmd = list(service_cmd) + [service_name, "restart"]
    util.subp(cmd)
    LOG.debug("Restarted the ssh daemon.")


def handle(_name, cfg, cloud, log, args):
    if len(args) != 0:
        # if run from command line, and give args, wipe the chpasswd['list']
        password = args[0]
        if 'chpasswd' in cfg and 'list' in cfg['chpasswd']:
            del cfg['chpasswd']['list']
    else:
        password = util.get_cfg_option_str(cfg, "password", None)

    expire = True
    plist = None

    if 'chpasswd' in cfg:
        chfg = cfg['chpasswd']
        if 'list' in chfg and chfg['list']:
            if isinstance(chfg['list'], list):
                log.debug("Handling input for chpasswd as list.")
                plist = util.get_cfg_option_list(chfg, 'list', plist)
            else:
                log.debug("Handling input for chpasswd as multiline string.")
                plist = util.get_cfg_option_str(chfg, 'list', plist)
                if plist:
                    plist = plist.splitlines()

        expire = util.get_cfg_option_bool(chfg, 'expire', expire)

    if not plist and password:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        if user:
            plist = ["%s:%s" % (user, password)]
        else:
            log.warn("No default or defined user to change password for.")

    errors = []
    if plist:
        plist_in = []
        hashed_plist_in = []
        hashed_users = []
        randlist = []
        users = []
        prog = re.compile(r'\$[1,2a,2y,5,6](\$.+){2}')
        for line in plist:
            u, p = line.split(':', 1)
            if prog.match(p) is not None and ":" not in p:
                hashed_plist_in.append("%s:%s" % (u, p))
                hashed_users.append(u)
            else:
                if p == "R" or p == "RANDOM":
                    p = rand_user_password()
                    randlist.append("%s:%s" % (u, p))
                plist_in.append("%s:%s" % (u, p))
                users.append(u)

        ch_in = '\n'.join(plist_in) + '\n'
        if users:
            try:
                log.debug("Changing password for %s:", users)
                util.subp(['chpasswd'], ch_in)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    log, "Failed to set passwords with chpasswd for %s", users)

        hashed_ch_in = '\n'.join(hashed_plist_in) + '\n'
        if hashed_users:
            try:
                log.debug("Setting hashed password for %s:", hashed_users)
                util.subp(['chpasswd', '-e'], hashed_ch_in)
            except Exception as e:
                errors.append(e)
                util.logexc(
                    log, "Failed to set hashed passwords with chpasswd for %s",
                    hashed_users)

        if len(randlist):
            blurb = ("Set the following 'random' passwords\n",
                     '\n'.join(randlist))
            sys.stderr.write("%s\n%s\n" % blurb)

        if expire:
            expired_users = []
            for u in users:
                try:
                    util.subp(['passwd', '--expire', u])
                    expired_users.append(u)
                except Exception as e:
                    errors.append(e)
                    util.logexc(log, "Failed to set 'expire' for %s", u)
            if expired_users:
                log.debug("Expired passwords for: %s users", expired_users)

    handle_ssh_pwauth(
        cfg.get('ssh_pwauth'), service_cmd=cloud.distro.init_cmd,
        service_name=cloud.distro.get_option('ssh_svcname', 'ssh'))

    if len(errors):
        log.debug("%s errors occured, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=9):
    return util.rand_str(pwlen, select_from=PW_SET)

# vi: ts=4 expandtab
