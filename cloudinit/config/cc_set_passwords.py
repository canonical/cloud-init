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
``username:RANDOM`` or ``username:R``. Password ssh authentication can be
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
        list:
            - user1:password1
            - user2:Random
            - user3:password3
            - user4:R
"""

import sys

from cloudinit.distros import ug_util
from cloudinit import ssh_util
from cloudinit import util

from string import ascii_letters, digits

# We are removing certain 'painful' letters/numbers
PW_SET = (''.join([x for x in ascii_letters + digits
                   if x not in 'loLOI01']))


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
        plist = util.get_cfg_option_str(chfg, 'list', plist)
        expire = util.get_cfg_option_bool(chfg, 'expire', expire)

    if not plist and password:
        (users, _groups) = ug_util.normalize_users_groups(cfg, cloud.distro)
        (user, _user_config) = ug_util.extract_default(users)
        if user:
            plist = "%s:%s" % (user, password)
        else:
            log.warn("No default or defined user to change password for.")

    errors = []
    if plist:
        plist_in = []
        randlist = []
        users = []
        for line in plist.splitlines():
            u, p = line.split(':', 1)
            if p == "R" or p == "RANDOM":
                p = rand_user_password()
                randlist.append("%s:%s" % (u, p))
            plist_in.append("%s:%s" % (u, p))
            users.append(u)

        ch_in = '\n'.join(plist_in) + '\n'
        try:
            log.debug("Changing password for %s:", users)
            util.subp(['chpasswd'], ch_in)
        except Exception as e:
            errors.append(e)
            util.logexc(log, "Failed to set passwords with chpasswd for %s",
                        users)

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

    change_pwauth = False
    pw_auth = None
    if 'ssh_pwauth' in cfg:
        if util.is_true(cfg['ssh_pwauth']):
            change_pwauth = True
            pw_auth = 'yes'
        elif util.is_false(cfg['ssh_pwauth']):
            change_pwauth = True
            pw_auth = 'no'
        elif str(cfg['ssh_pwauth']).lower() == 'unchanged':
            log.debug('Leaving auth line unchanged')
            change_pwauth = False
        elif not str(cfg['ssh_pwauth']).strip():
            log.debug('Leaving auth line unchanged')
            change_pwauth = False
        elif not cfg['ssh_pwauth']:
            log.debug('Leaving auth line unchanged')
            change_pwauth = False
        else:
            msg = 'Unrecognized value %s for ssh_pwauth' % cfg['ssh_pwauth']
            util.logexc(log, msg)

    if change_pwauth:
        replaced_auth = False

        # See: man sshd_config
        old_lines = ssh_util.parse_ssh_config(ssh_util.DEF_SSHD_CFG)
        new_lines = []
        i = 0
        for (i, line) in enumerate(old_lines):
            # Keywords are case-insensitive and arguments are case-sensitive
            if line.key == 'passwordauthentication':
                log.debug("Replacing auth line %s with %s", i + 1, pw_auth)
                replaced_auth = True
                line.value = pw_auth
            new_lines.append(line)

        if not replaced_auth:
            log.debug("Adding new auth line %s", i + 1)
            replaced_auth = True
            new_lines.append(ssh_util.SshdConfigLine('',
                                                     'PasswordAuthentication',
                                                     pw_auth))

        lines = [str(l) for l in new_lines]
        util.write_file(ssh_util.DEF_SSHD_CFG, "\n".join(lines))

        try:
            cmd = cloud.distro.init_cmd  # Default service
            cmd.append(cloud.distro.get_option('ssh_svcname', 'ssh'))
            cmd.append('restart')
            if 'systemctl' in cmd:  # Switch action ordering
                cmd[1], cmd[2] = cmd[2], cmd[1]
            cmd = filter(None, cmd)  # Remove empty arguments
            util.subp(cmd)
            log.debug("Restarted the ssh daemon")
        except Exception:
            util.logexc(log, "Restarting of the ssh daemon failed")

    if len(errors):
        log.debug("%s errors occured, re-raising the last one", len(errors))
        raise errors[-1]


def rand_user_password(pwlen=9):
    return util.rand_str(pwlen, select_from=PW_SET)

# vi: ts=4 expandtab
